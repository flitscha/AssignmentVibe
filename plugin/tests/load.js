// Loads a QML `.pragma library` JS file under node. QML-only directives are
// stripped, `.import "X.js" as X` becomes a parameter, and every top-level
// function and var is returned as the module object.
const fs = require("fs")
const path = require("path")

const cache = {}

function load(name) {
  if (cache[name]) return cache[name]
  const file = path.join(__dirname, "..", name)
  const source = fs.readFileSync(file, "utf8")
  const imports = []
  const body = source.split("\n").map(line => {
    const m = /^\.import\s+"([^"]+)"\s+as\s+(\w+)/.exec(line)
    if (m) { imports.push([m[1], m[2]]); return "" }
    return line.startsWith(".pragma") ? "" : line
  }).join("\n")
  const names = [...body.matchAll(/^(?:function|var)\s+(\w+)/gm)].map(m => m[1])
  const factory = new Function(...imports.map(i => i[1]), body + "\nreturn {" + names.join(",") + "}")
  cache[name] = factory(...imports.map(i => load(i[0])))
  return cache[name]
}

module.exports = load
