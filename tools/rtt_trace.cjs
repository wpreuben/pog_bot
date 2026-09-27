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

function isOldApCombatResponse(replay, index, state, role, name, pending) {
    const next = replay[index + 1]
    return pending === null && role === "Central Powers" &&
        (name === "attack" || name === "flank" || name === "pass") &&
        state.state === "confirm_mo" && state.active === "Allied Powers" &&
        state.ap_mo_confirmation_needed === true &&
        state.ap_mo_return_state === "defender_combat_cards" &&
        Array.isArray(next) && next[0] === "Allied Powers" &&
        ((next.length === 2 && next[1] === "done") ||
         (next.length === 3 && next[1] === "card" && Number.isInteger(next[2])))
}

function confirmOldApCombatResponse(rules, state) {
    const before = JSON.parse(JSON.stringify(state))
    const confirmed = rules.action(state, "Allied Powers", "next")
    if (confirmed.state !== "defender_combat_cards" ||
        Object.hasOwn(confirmed, "ap_mo_confirmation_needed") ||
        Object.hasOwn(confirmed, "ap_mo_return_state"))
        throw new Error("AP mandatory offensive compatibility transition changed")
    const original = { ...before }
    const result = { ...confirmed }
    for (const key of ["state", "ap_mo_confirmation_needed", "ap_mo_return_state"]) {
        delete original[key]
        delete result[key]
    }
    if (JSON.stringify(original) !== JSON.stringify(result))
        throw new Error("AP mandatory offensive compatibility changed semantic state")
    return confirmed
}

function isDelayedApConfirmation(replay, index, state, role, name, pending) {
    const previous = replay[index - 1]
    const next = replay[index + 1]
    return pending !== null && state.turn === pending.turn && index > pending.index &&
        role === "Allied Powers" && name === "next" &&
        replay[index].length === 2 && state.state === "action_phase" &&
        state.active === "Allied Powers" &&
        !Object.hasOwn(state, "ap_mo_confirmation_needed") &&
        !Object.hasOwn(state, "ap_mo_return_state") &&
        Array.isArray(previous) && previous[0] === "Central Powers" &&
        previous[1] === "end_action" &&
        Array.isArray(next) && next[0] === "Allied Powers" &&
        ["play_ops", "play_event", "play_sr", "play_rps", "single_op",
         "done", "flag_supply_warnings"].includes(next[1])
}

function main() {
    if (process.argv.length !== 4)
        throw new Error("usage: node rtt_trace.cjs <replay.json> <rules.js>")
    const fixture = JSON.parse(fs.readFileSync(process.argv[2], "utf8"))
    if (!Array.isArray(fixture.replay))
        throw new Error("replay array is required")
    const rules = require(path.resolve(process.argv[3]))
    let state = null
    let pendingMo = null
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
            else if (isDelayedApConfirmation(fixture.replay, index, state, role,
                                              name, pendingMo))
                pendingMo = null
            else
                state = rules.action(state, role, name, argument)
            if (state !== null && isOldApCombatResponse(fixture.replay, index, state,
                                                         role, name, pendingMo)) {
                state = confirmOldApCombatResponse(rules, state)
                pendingMo = { turn: state.turn, index }
            }
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
