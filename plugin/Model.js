.pragma library

// The context editor's logic, apart from any QML so it runs under node
// (tests/model.test.js). The backend sends the whole outline once (api.py,
// context_payload); ticking happens here, locally, and only the result goes
// back - a round trip per tick would lag.
//
// A selection is
//   { ids: {id: true}, proofOf: {id: true}, allProofs: bool, earlier: {ref: true} }
// with statement ids like "Satz 3.1.5" and earlier-task refs like
// "optimierung/01-Blatt#2". As in the backend, the selection is a set of
// statements and nothing else: a chapter's box is ticked when all of its
// statements are, which is what lets one statement be unticked out of a whole
// chapter.

var OFF = 0
var SOME = 1
var ALL = 2

function covers(selected, key) {
  return key === selected || key.indexOf(selected + ".") === 0
}

function kilo(chars) {
  if (chars <= 0) return "0k"
  if (chars < 100) return "<0.1k"
  return (chars / 1000).toFixed(1) + "k"
}

function plural(n, noun) {
  return n + " " + noun + (n === 1 ? "" : "s")
}

function selectionFrom(ctx) {
  var sel = { ids: {}, proofOf: {}, allProofs: !!ctx.allProofs, earlier: {} }
  ;(ctx.selected || []).forEach(function(id) { sel.ids[id] = true })
  ;(ctx.proofOf || []).forEach(function(id) { sel.proofOf[id] = true })
  ;(ctx.earlierSelected || []).forEach(function(ref) { sel.earlier[ref] = true })
  return sel
}

function copySelection(sel) {
  return {
    ids: Object.assign({}, sel.ids),
    proofOf: Object.assign({}, sel.proofOf),
    allProofs: sel.allProofs,
    earlier: Object.assign({}, sel.earlier)
  }
}

// What goes back to the backend (api.py, "set_selection").
function toRequest(sel) {
  return {
    ids: Object.keys(sel.ids),
    proofOf: Object.keys(sel.proofOf),
    allProofs: sel.allProofs,
    earlier: Object.keys(sel.earlier)
  }
}

// ---- The outline -------------------------------------------------------------

// A statement is listed if it counts under the algorithms switch, or if it was
// picked by name anyway (the backend keeps those, see selection.chosen).
function counts(ctx, sel, s) {
  return !s.algorithm || ctx.algorithms || !!sel.ids[s.id]
}

// Lookups built once per payload: statements by id, each node's parent and
// children, the statements directly in a node, and all statements beneath it.
function index(ctx) {
  var byId = {}
  ctx.statements.forEach(function(s) { byId[s.id] = s })

  var nodeKeys = {}
  ctx.nodes.forEach(function(n) { nodeKeys[n.key] = n })

  function parentOf(key) {
    var parts = key.split(".")
    while (parts.length > 1) {
      parts.pop()
      var k = parts.join(".")
      if (nodeKeys[k]) return k
    }
    return null
  }

  // The deepest node covering a section key. A statement filed under a
  // section the outline does not list lands in its nearest listed ancestor.
  function home(section) {
    if (!section) return null
    if (nodeKeys[section]) return section
    return parentOf(section)
  }

  var children = {}
  var roots = []
  ctx.nodes.forEach(function(n) {
    var p = parentOf(n.key)
    if (p) (children[p] = children[p] || []).push(n.key)
    else roots.push(n.key)
  })

  var direct = {}
  var loose = []
  ctx.statements.forEach(function(s) {
    var h = home(s.section)
    if (h) (direct[h] = direct[h] || []).push(s.id)
    else loose.push(s.id)
  })

  var beneath = {}
  ctx.nodes.forEach(function(n) {
    beneath[n.key] = ctx.statements.filter(function(s) {
      return s.section && covers(n.key, s.section)
    }).map(function(s) { return s.id })
  })

  var earlierBySheet = {}
  var sheets = []
  ;(ctx.earlier || []).forEach(function(t) {
    if (!earlierBySheet[t.sheet]) {
      earlierBySheet[t.sheet] = []
      sheets.push(t.sheet)
    }
    earlierBySheet[t.sheet].push(t)
  })

  return {
    byId: byId, nodes: nodeKeys, children: children, roots: roots,
    direct: direct, loose: loose, beneath: beneath,
    earlierBySheet: earlierBySheet, sheets: sheets
  }
}

function nodeLabel(node) {
  if (node.title) return node.key + " " + node.title
  return (node.level === 1 ? "Kapitel " : "Abschnitt ") + node.key
}

function listed(ctx, idx, sel, ids) {
  return ids.filter(function(id) { return counts(ctx, sel, idx.byId[id]) })
}

function tri(ids, marks) {
  var on = 0
  for (var i = 0; i < ids.length; i++) if (marks[ids[i]]) on++
  if (on === 0) return OFF
  return on === ids.length ? ALL : SOME
}

// A proof that only says where the proof is ("Übung.", "Siehe Aufgabe 3.4")
// is not offered: in a prompt it helps nobody.
function hasProof(s) {
  return s.proofSize > 0 && !s.referral
}

function proofOn(sel, id) {
  return sel.allProofs || !!sel.proofOf[id]
}

function statementSize(sel, s) {
  return s.size + (s.proofSize && proofOn(sel, s.id) ? s.proofSize : 0)
}

// ---- Totals ------------------------------------------------------------------

function totals(ctx, idx, sel) {
  var statements = 0, proofs = 0, size = 0, withProof = 0
  for (var id in sel.ids) {
    var s = idx.byId[id]
    if (!s) continue
    statements++
    size += statementSize(sel, s)
    if (hasProof(s)) {
      withProof++
      if (proofOn(sel, id)) proofs++
    }
  }
  var earlier = 0
  for (var ref in sel.earlier) earlier++
  return { statements: statements, proofs: proofs, withProof: withProof,
           earlier: earlier, size: size }
}

// ---- Edits (each returns a new selection) -------------------------------------

function toggleIds(sel, ids) {
  var next = copySelection(sel)
  var allOn = ids.length > 0 && tri(ids, sel.ids) === ALL
  ids.forEach(function(id) {
    if (allOn) delete next.ids[id]
    else next.ids[id] = true
  })
  return next
}

function toggleNode(ctx, idx, sel, key) {
  return toggleIds(sel, listed(ctx, idx, sel, idx.beneath[key] || []))
}

// A proof without its statement is unreadable, so ticking a proof ticks the
// statement too. Unticking one proof while "all proofs" is on turns that into
// the explicit list of all the others.
function toggleProof(ctx, idx, sel, id) {
  var next = copySelection(sel)
  if (proofOn(sel, id)) {
    if (next.allProofs) {
      next.allProofs = false
      for (var other in next.ids) {
        var s = idx.byId[other]
        if (s && hasProof(s) && other !== id) next.proofOf[other] = true
      }
    }
    delete next.proofOf[id]
  } else {
    next.proofOf[id] = true
    next.ids[id] = true
  }
  return next
}

function toggleEarlier(sel, refs) {
  var next = copySelection(sel)
  var allOn = refs.length > 0 && tri(refs, sel.earlier) === ALL
  refs.forEach(function(ref) {
    if (allOn) delete next.earlier[ref]
    else next.earlier[ref] = true
  })
  return next
}

function setAllProofs(sel, on) {
  var next = copySelection(sel)
  next.allProofs = on
  if (!on) next.proofOf = {}
  return next
}

function cleared() {
  return { ids: {}, proofOf: {}, allProofs: false, earlier: {} }
}

// ---- Rows --------------------------------------------------------------------

// Nodes worth opening on arrival: those only partly chosen - where a pick by
// Jev or by hand sits among statements that were left out.
function initiallyExpanded(ctx, idx, sel) {
  var open = {}
  ctx.nodes.forEach(function(n) {
    if (tri(listed(ctx, idx, sel, idx.beneath[n.key]), sel.ids) === SOME)
      open["n:" + n.key] = true
  })
  idx.sheets.forEach(function(sheet) {
    var refs = idx.earlierBySheet[sheet].map(function(t) { return t.ref })
    if (tri(refs, sel.earlier) === SOME) open["s:" + sheet] = true
  })
  return open
}

function statementRow(ctx, idx, sel, id, level, caption) {
  var s = idx.byId[id]
  return {
    kind: "statement", id: id, level: level,
    label: id, about: s.name || s.text, caption: caption || "",
    on: !!sel.ids[id],
    algorithm: s.algorithm,
    hasProof: hasProof(s),
    proofOn: hasProof(s) && proofOn(sel, id),
    proofText: "proof " + kilo(s.proofSize),
    size: kilo(s.size)
  }
}

function matches(s, needle) {
  return (s.id + " " + s.name + " " + s.text).toLowerCase().indexOf(needle) >= 0
}

function sectionCaption(ctx, idx, s) {
  var n = idx.nodes[s.section]
  return n ? nodeLabel(n) : (s.section ? "Section " + s.section : "")
}

// Everything the list shows, top to bottom. `mode` is "all" (the outline) or
// "chosen" (only what is ticked); a `query` lists matching statements flat.
function rows(ctx, idx, sel, expanded, query, mode) {
  var out = []
  var needle = (query || "").trim().toLowerCase()
  var visible = ctx.statements.filter(function(s) { return counts(ctx, sel, s) })

  if (needle || mode === "chosen") {
    var found = visible.filter(function(s) {
      return (mode !== "chosen" || sel.ids[s.id]) && (!needle || matches(s, needle))
    })
    if (ctx.statements.length) {
      out.push({ kind: "header", text: needle ? "Matching statements" : "Chosen statements",
                 detail: plural(found.length, "statement") })
      found.forEach(function(s) {
        out.push(statementRow(ctx, idx, sel, s.id, 0, sectionCaption(ctx, idx, s)))
      })
      if (!found.length)
        out.push({ kind: "empty", text: needle ? "No statement matches “" + query.trim() + "”."
                                               : "Nothing chosen yet." })
    }
    var tasks = (ctx.earlier || []).filter(function(t) {
      return (mode !== "chosen" || sel.earlier[t.ref])
        && (!needle || (t.title + " " + t.text).toLowerCase().indexOf(needle) >= 0)
    })
    if (tasks.length) {
      out.push({ kind: "header", text: "Earlier tasks", detail: plural(tasks.length, "task") })
      tasks.forEach(function(t) { out.push(earlierRow(sel, t, 0, true)) })
    }
    return out
  }

  if (ctx.statements.length) {
    out.push({ kind: "header", text: "Lecture notes",
               detail: plural(visible.length, "statement") })
    var walk = function(key, level) {
      var node = idx.nodes[key]
      var ids = listed(ctx, idx, sel, idx.beneath[key] || [])
      if (!ids.length) return
      var open = !!expanded["n:" + key]
      var size = 0
      ids.forEach(function(id) { size += idx.byId[id].size })
      var on = ids.filter(function(id) { return sel.ids[id] }).length
      out.push({ kind: "node", key: key, level: level, label: nodeLabel(node),
                 state: tri(ids, sel.ids), expanded: open,
                 count: on + "/" + ids.length, size: kilo(size) })
      if (!open) return
      ;(idx.children[key] || []).forEach(function(child) { walk(child, level + 1) })
      listed(ctx, idx, sel, idx.direct[key] || []).forEach(function(id) {
        out.push(statementRow(ctx, idx, sel, id, level + 1))
      })
    }
    idx.roots.forEach(function(key) { walk(key, 0) })
    listed(ctx, idx, sel, idx.loose).forEach(function(id) {
      out.push(statementRow(ctx, idx, sel, id, 0, "not in the outline"))
    })
  }

  if (!ctx.statements.length && idx.sheets.length) {
    out.push({ kind: "header", text: "Lecture notes", detail: "" })
    out.push({ kind: "empty", text: "None read in for this course. If uni.json names its "
                                  + "script, Setup › Read in new PDFs reads it." })
  }

  if (idx.sheets.length) {
    out.push({ kind: "header", text: "Earlier sheets",
               detail: "only the task text goes in" })
    idx.sheets.forEach(function(sheet) {
      var tasks = idx.earlierBySheet[sheet]
      var refs = tasks.map(function(t) { return t.ref })
      var open = !!expanded["s:" + sheet]
      var on = refs.filter(function(r) { return sel.earlier[r] }).length
      out.push({ kind: "sheet", key: sheet, level: 0, label: "Sheet " + sheet,
                 state: tri(refs, sel.earlier), expanded: open,
                 count: on + "/" + refs.length, size: "" })
      if (open) tasks.forEach(function(t) { out.push(earlierRow(sel, t, 1, false)) })
    })
  }

  if (!out.length)
    out.push({ kind: "empty", text: "No lecture notes read in for this course, and no earlier "
                                  + "sheets - the prompt carries the task alone." })
  return out
}

function earlierRow(sel, t, level, withSheet) {
  return {
    kind: "earlier", ref: t.ref, level: level,
    label: (withSheet ? "Sheet " + t.sheet + ", task " : "Task ") + t.task,
    about: t.title || t.text, caption: "", on: !!sel.earlier[t.ref]
  }
}

function sheetRefs(idx, sheet) {
  return idx.earlierBySheet[sheet].map(function(t) { return t.ref })
}
