// Test harness: executes the dispatch-batch workflow body the way the
// workflow runtime does (AsyncFunction with injected globals), with stubbed
// agent()/pipeline() so behavior is driven by a scenario JSON argument.
//
// Usage: node dispatch_batch_harness.js <workflow.js path> <scenario JSON>
// Scenario: {
//   args: any,                    // passed verbatim as the `args` global
//   stringifyArgs: bool,          // JSON-encode args before injection
//   agents: { "<packet_id>": ["throw"|"null"|"ok", ...] },  // per-call plan
//   envelopes: { "<packet_id>": object },  // envelope returned on "ok"
// }
// Prints JSON: { result, calls, notes, error }.
'use strict'

const fs = require('fs')

const [, , workflowPath, scenarioJson] = process.argv
const scenario = JSON.parse(scenarioJson)
const source = fs.readFileSync(workflowPath, 'utf8')
const body = source.replace(/^export const meta/m, 'const meta')

const calls = []
const notes = []

function agentStub(prompt, opts) {
  const label = (opts && opts.label) || ''
  const packetId = label.split(':')[0]
  const plan = scenario.agents && scenario.agents[packetId]
  const step = plan && plan.length ? plan.shift() : 'ok'
  calls.push({
    packet_id: packetId,
    label,
    agentType: (opts && opts.agentType) || null,
    schemaRequired: (opts && opts.schema && opts.schema.required) || null,
    behavior: step,
  })
  if (step === 'throw') return Promise.reject(new Error('API Error: Overloaded'))
  if (step === 'null') return Promise.resolve(null)
  return Promise.resolve({
    envelope: (scenario.envelopes && scenario.envelopes[packetId]) || {},
    output: {},
  })
}

// Mirrors the documented runtime semantics: stages run per item with no
// barrier, and a stage that throws drops that item to null.
async function pipelineStub(items, ...stages) {
  return Promise.all(
    items.map(async (item, index) => {
      let value = item
      for (const stage of stages) {
        try {
          value = await stage(value, item, index)
        } catch (error) {
          return null
        }
      }
      return value
    }),
  )
}

async function parallelStub(thunks) {
  return Promise.all(thunks.map(thunk => thunk().catch(() => null)))
}

const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor
const run = new AsyncFunction(
  'agent',
  'pipeline',
  'parallel',
  'phase',
  'log',
  'args',
  'budget',
  'workflow',
  body,
)

const injectedArgs = scenario.stringifyArgs ? JSON.stringify(scenario.args) : scenario.args

run(
  agentStub,
  pipelineStub,
  parallelStub,
  () => {},
  message => notes.push(String(message)),
  injectedArgs,
  { total: null, spent: () => 0, remaining: () => Infinity },
  () => {
    throw new Error('nested workflow() not available')
  },
)
  .then(result => {
    process.stdout.write(JSON.stringify({ result, calls, notes, error: null }))
  })
  .catch(error => {
    process.stdout.write(
      JSON.stringify({ result: null, calls, notes, error: String((error && error.message) || error) }),
    )
  })
