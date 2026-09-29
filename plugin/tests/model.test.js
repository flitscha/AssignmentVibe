// node plugin/tests/model.test.js
const assert = require("assert")
const M = require("./load")("Model.js")

const ctx = {
  algorithms: false,
  allProofs: false,
  nodes: [
    { key: "1", title: "Konvexe Mengen", level: 1 },
    { key: "1.1", title: "Polyeder", level: 2 },
    { key: "1.2", title: "Ecken", level: 2 },
    { key: "2", title: "", level: 1 },
  ],
  statements: [
    { id: "Definition 1.1.1", name: "", text: "Halbraum", section: "1.1", algorithm: false, size: 100, proofSize: 0 },
    { id: "Satz 1.1.2", name: "Minkowski", text: "…", section: "1.1", algorithm: false, size: 200, proofSize: 500 },
    { id: "Satz 1.2.1", name: "", text: "Ecke", section: "1.2", algorithm: false, size: 300, proofSize: 50 },
    { id: "Lemma 1.3", name: "", text: "direct in 1", section: "1.3", algorithm: false, size: 10, proofSize: 20, referral: true },
    { id: "Algorithmus 2.1", name: "Simplex", text: "", section: "2", algorithm: true, size: 1000, proofSize: 0 },
  ],
  selected: ["Satz 1.1.2"],
  proofOf: [],
  earlier: [
    { ref: "c/B1#1", sheet: "1", task: 1, title: "", text: "Zeige" },
    { ref: "c/B1#2", sheet: "1", task: 2, title: "Titel", text: "Rechne" },
  ],
  earlierSelected: [],
}

const idx = M.index(ctx)
assert.deepStrictEqual(idx.roots, ["1", "2"])
assert.deepStrictEqual(idx.children["1"], ["1.1", "1.2"])
assert.deepStrictEqual(idx.direct["1"], ["Lemma 1.3"], "a section the outline lacks lands in its parent")
assert.deepStrictEqual(idx.beneath["1"].length, 4)

let sel = M.selectionFrom(ctx)
assert.strictEqual(M.totals(ctx, idx, sel).size, 200)

// Chapter 1 is partly chosen, so it opens; chapter 2 only has an algorithm,
// which does not count while algorithms are off.
const open = M.initiallyExpanded(ctx, idx, sel)
assert.ok(open["n:1"] && open["n:1.1"] && !open["n:1.2"])
let rows = M.rows(ctx, idx, sel, open, "", "all")
assert.deepStrictEqual(rows.map(r => r.kind + ":" + (r.key || r.id || r.text)), [
  "header:Lecture notes", "node:1", "node:1.1", "statement:Definition 1.1.1",
  "statement:Satz 1.1.2", "node:1.2", "statement:Lemma 1.3",
  "header:Earlier sheets", "sheet:1",
])
assert.strictEqual(rows[1].state, M.SOME)
assert.strictEqual(rows[1].count, "1/4")

// Ticking a partly chosen chapter chooses all of it; ticking again clears it.
sel = M.toggleNode(ctx, idx, sel, "1")
assert.strictEqual(M.tri(idx.beneath["1"], sel.ids), M.ALL)
sel = M.toggleNode(ctx, idx, sel, "1")
assert.strictEqual(Object.keys(sel.ids).length, 0)

// A proof brings its statement along.
sel = M.toggleProof(ctx, idx, sel, "Satz 1.1.2")
assert.ok(sel.ids["Satz 1.1.2"] && sel.proofOf["Satz 1.1.2"])
assert.strictEqual(M.totals(ctx, idx, sel).size, 700)

// Unticking one proof under "all proofs" keeps the others.
sel = M.toggleIds(sel, ["Satz 1.2.1"])
sel = M.setAllProofs(sel, true)
sel = M.toggleProof(ctx, idx, sel, "Satz 1.1.2")
assert.ok(!sel.allProofs && sel.proofOf["Satz 1.2.1"] && !sel.proofOf["Satz 1.1.2"])

// A proof that only points elsewhere ("Übung.") is not offered.
rows = M.rows(ctx, idx, sel, { "n:1": true, "n:1.1": true }, "", "all")
assert.strictEqual(rows.find(r => r.id === "Lemma 1.3").hasProof, false)
assert.strictEqual(rows.find(r => r.id === "Satz 1.1.2").hasProof, true)

// An algorithm picked by name shows although algorithms are off.
sel = M.toggleIds(sel, ["Algorithmus 2.1"])
rows = M.rows(ctx, idx, sel, {}, "", "all")
assert.ok(rows.some(r => r.kind === "node" && r.key === "2"))

// Search lists matches flat, with where they are from.
rows = M.rows(ctx, idx, M.cleared(), {}, "minkowski", "all")
assert.deepStrictEqual(rows.map(r => r.kind), ["header", "statement"])
assert.strictEqual(rows[1].caption, "1.1 Polyeder")

// "Chosen" shows only what is ticked, earlier tasks included.
sel = M.toggleEarlier(M.cleared(), ["c/B1#2"])
rows = M.rows(ctx, idx, sel, {}, "", "chosen")
assert.deepStrictEqual(rows.map(r => r.kind), ["header", "empty", "header", "earlier"])
assert.strictEqual(rows[3].label, "Sheet 1, task 2")

assert.deepStrictEqual(M.toRequest(sel), { ids: [], proofOf: [], allProofs: false, earlier: ["c/B1#2"] })
assert.strictEqual(M.kilo(1234), "1.2k")
assert.strictEqual(M.kilo(40), "<0.1k")
console.log("model: all passed")

// Effort colours run from green to red; dependencies read as sentences.
assert.deepStrictEqual(M.effortHsl(1).map(x => +x.toFixed(3)), [0.333, 0.62, 0.58])
assert.strictEqual(M.effortHsl(10)[0], 0)
assert.strictEqual(M.effortHsl(12)[0], 0)
assert.strictEqual(M.dependencyText([{ number: 1, after: [] }, { number: 3, after: [2] }, { number: 5, after: [1, 3] }]),
                   "3 builds on 2  ·  5 builds on 1, 3")
console.log("effort: all passed")
