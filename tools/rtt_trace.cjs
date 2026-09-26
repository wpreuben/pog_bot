"use strict"

// Read-only bridge to the separately supplied Rally the Troops reference engine.
const fs = require("node:fs")
const path = require("node:path")

function observe(state) {
    if (state === null)
        return null
    const copy = { ...state }
    delete copy.log
    delete copy.undo
    return JSON.parse(JSON.stringify(copy))
}

function randomSeeds(before, after, name) {
    if (before === after)
        return []
    let seed = before
    const visited = []
    for (let count = 0; count < 1000; ++count) {
        seed = seed * 200105 % 34359738337
        visited.push(seed)
        if (seed === after)
            return visited
    }
    if (name === "undo")
        return []
    throw new Error(`RNG state cannot be traced: ${before} → ${after}`)
}

function main() {
    if (process.argv.length !== 4)
        throw new Error("usage: node rtt_trace.cjs <replay.json> <rules.js>")
    const fixture = JSON.parse(fs.readFileSync(process.argv[2], "utf8"))
    if (!Array.isArray(fixture.replay))
        throw new Error("replay array is required")
    const rules = require(path.resolve(process.argv[3]))
    let state = null
    for (let index = 0; index < fixture.replay.length; ++index) {
        const row = fixture.replay[index]
        try {
            if (!Array.isArray(row) || row.length < 2 || row.length > 3)
                throw new Error("invalid replay row")
            const [role, name, argument] = row
            const before = observe(state)
            const logLength = state === null ? 0 : state.log.length
            const seedBefore = state === null ? argument?.[0] : state.seed
            if (name === ".setup")
                state = rules.setup(...argument)
            else if (name === ".resign")
                state = rules.resign(state, role)
            else
                state = rules.action(state, role, name, argument)
            const after = observe(state)
            const seeds = randomSeeds(seedBefore, state.seed, name)
            process.stdout.write(JSON.stringify({
                index, role, name, argument: argument ?? null, before, after,
                log_delta: state.log.slice(logLength),
                random: { before: seedBefore, after: state.seed, seeds },
            }) + "\n")
        } catch (error) {
            throw new Error(`index ${index}: ${error.message}`)
        }
    }
    process.stdout.write(JSON.stringify({
        kind: "final", turn: state.turn, vp: state.vp, state: state.state,
        victory: state.victory, seed: state.seed,
    }) + "\n")
}

try {
    main()
} catch (error) {
    process.stderr.write(`${error.message}\n`)
    process.exitCode = 1
}
