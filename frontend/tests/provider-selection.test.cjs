// Exercise App's real event handlers and request serialization without a DOM.
// The hook harness queues updates until render, matching React's event batching.
const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const jsx = require('react/jsx-runtime');

function mountApp(options = {}) {
  const effects = [];
  let mounted = false;
  const saved = new Map(options.activeRun ? [['review-board-active-run', options.activeRun]] : []);
  const localStorage = { getItem: key => saved.get(key), setItem: (key, value) => saved.set(key, value), removeItem: key => saved.delete(key) };
  const state = [];
  const pending = [];
  const requests = [];
  let cursor = 0;
  const hooks = {
    useEffect(effect) { if (options.runEffects && !mounted) effects.push(effect); },
    useState(initial) {
      const index = cursor++;
      if (!(index in state)) state[index] = initial;
      return [state[index], update => pending.push(() => {
        state[index] = typeof update === 'function' ? update(state[index]) : update;
      })];
    },
  };
  const exports = {};
  const source = fs.readFileSync(path.join(__dirname, '../src/App.tsx'), 'utf8');
  const compiled = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX,
    target: ts.ScriptTarget.ES2020, esModuleInterop: true,
  } }).outputText;
  const panel = Array.from({ length: 3 }, (_, i) => ({
    id: `spec_${i + 1}`, role: `Specialist ${i + 1}`, expertise: 'Expertise',
    mandate: 'Mandate', rationale: 'Rationale', provider: 'mock', model: 'mock-deterministic',
  }));
  vm.runInNewContext(compiled, {
    exports, console, TextDecoder, crypto: require('node:crypto').webcrypto,
    require(name) {
      if (name === './reviewExecution') {
        const helper = {};
        const source = fs.readFileSync(path.join(__dirname, '../src/reviewExecution.ts'), 'utf8');
        vm.runInNewContext(ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText,
          { exports: helper, TextDecoder, setTimeout, localStorage, fetch: async (url, requestOptions) => {
            if (options.fetcher) {
              requests.push({ url, options: requestOptions });
              return options.fetcher(url, requestOptions);
            }
            requests.push({ url, options: requestOptions });
            const payload = JSON.parse(requestOptions.body);
            return { ok: true, json: async () => ({ session_id: payload.session_id, status: 'completed', specialist_reviews: [], challenge_round: [], execution_summary: { calls_made: 0, total_latency_ms: 0, total_tokens: 0, total_cost_usd: 0 }, run_metadata: { sequence: 1 } }) };
          } });
        return helper;
      }
      if (name === 'react') return hooks;
      if (name === 'react/jsx-runtime') return jsx;
      if (name === 'lucide-react') return new Proxy({}, { get: (_, key) => key });
      throw Error(`Unexpected import ${name}`);
    },
    async fetch(url, requestOptions) {
      requests.push({ url, options: requestOptions });
      if (options.fetcher) return options.fetcher(url, requestOptions);
      if (url.endsWith('/generate-panel')) return { ok: true, json: async () => panel };
      if (url.endsWith('/run-stream')) return {
        ok: true, body: { getReader: () => ({ read: async () => ({ done: true }) }) },
      };
      return { ok: true, json: async () => [] };
    },
  });
  function render() {
    pending.splice(0).forEach(update => update());
    cursor = 0;
    const tree = exports.default();
    if (!mounted) {
      mounted = true;
      effects.splice(0).forEach(effect => effect());
    }
    return tree;
  }
  return { render, requests };
}
function elements(node, predicate) {
  if (!node || typeof node !== 'object') return [];
  if (Array.isArray(node)) return node.flatMap(child => elements(child, predicate));
  return [...(predicate(node) ? [node] : []), ...elements(node.props?.children, predicate)];
}
function label(node) {
  if (Array.isArray(node)) return node.map(label).join('');
  if (node && typeof node === 'object') return label(node.props?.children);
  return node == null ? '' : String(node);
}
function button(tree, text) {
  return elements(tree, e => e.type === 'button' && label(e).includes(text))[0];
}

test('provider/model switches remain paired in the outgoing review request', async () => {
  const app = mountApp();
  let tree = app.render();
  const textInputs = elements(tree, e => e.type === 'input' && e.props.type === 'text');
  textInputs[0].props.onChange({ target: { value: 'Test startup' } });
  tree = app.render();
  elements(tree, e => e.type === 'textarea' && e.props.placeholder === 'Detailed architecture or business model description...')[0].props.onChange({ target: { value: 'Test startup description' } });
  tree = app.render();
  await button(tree, 'Generate 3–5 Specialist Panel').props.onClick();
  tree = app.render();
  for (const [provider, model] of [
    ['openai', 'gpt-4o-mini'], ['gemini', 'gemini-1.5-flash'], ['mock', 'mock-deterministic'],
  ]) {
    const providerSelect = elements(tree, e => e.type === 'select'
      && label(e).includes('OpenAI (AsyncOpenAI)'))[0];
    providerSelect.props.onChange({ target: { value: provider } });
    tree = app.render();
    await button(tree, 'Run Review Board').props.onClick();
    const request = app.requests.filter(r => r.url.endsWith('/runs')).at(-1);
    const sentPanel = JSON.parse(request.options.body).panel;
    assert.equal(sentPanel[0].provider, provider);
    assert.equal(sentPanel[0].model, model);
    assert.equal(sentPanel[0].role, 'Specialist 1');
    assert.equal(sentPanel[1].provider, 'mock');
    assert.equal(sentPanel[1].model, 'mock-deterministic');
    tree = app.render();
  }
});

const json = value => ({ ok: true, json: async () => value });
const deferred = () => {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return { promise, resolve };
};
const flush = () => new Promise(resolve => setImmediate(resolve));
const presetIdea = {
  title: 'Default DevPulse', idea: 'Default developer tool description', target_customer: 'Developers',
  problem: 'Default problem', proposed_solution: 'Default solution', evidence: [],
};
function savedSession() {
  return {
    session_id: 'saved-run', status: 'completed', created_at: '2026-11-06T00:00:00Z',
    idea: { ...presetIdea, title: 'Recovered GlowGreen' },
    panel: Array.from({ length: 3 }, (_, i) => ({
      id: `spec_${i}`, role: `Recovered specialist ${i}`, expertise: 'Recovery expertise',
      mandate: 'Recovery mandate', rationale: 'Recovery rationale', provider: 'mock', model: 'mock-deterministic',
    })),
    specialist_reviews: [], challenge_round: [],
    budget_config: { call_cap: 20, token_cap: 50000, timeout_seconds: 12, max_retries: 1 },
    execution_summary: { calls_made: 3, total_latency_ms: 150, total_tokens: 600,
      total_cost_usd: 0.001, reported_tokens: 100, estimated_tokens: 200, simulated_tokens: 300 },
    run_metadata: { sequence: 9 },
  };
}

for (const first of ['presets', 'recovery']) {
  test(`mount recovery preserves saved idea and panel when ${first} finishes first`, async () => {
    const presets = deferred();
    const recovery = deferred();
    const app = mountApp({ runEffects: true, activeRun: 'saved-run', fetcher: async url => {
      if (url.endsWith('/presets')) return presets.promise;
      if (url.endsWith('/sessions/saved-run')) return recovery.promise;
      if (url.endsWith('/sessions')) return json([]);
      throw Error(`Unexpected request ${url}`);
    } });
    app.render();
    const finish = {
      presets: () => presets.resolve(json({ devtool_ebpf: { name: 'DevPulse', description: 'Default', idea: presetIdea } })),
      recovery: () => recovery.resolve(json(savedSession())),
    };
    finish[first]();
    await flush();
    app.render();
    finish[first === 'presets' ? 'recovery' : 'presets']();
    await flush();
    const tree = app.render();
    assert(elements(tree, e => e.type === 'input' && e.props.value === 'Recovered GlowGreen').length);
    assert(elements(tree, e => e.type === 'input' && e.props.value === 'Recovered specialist 0').length);
    assert.match(label(tree), /Status: completed/);
    assert.equal(app.requests.filter(r => r.options?.method === 'POST').length, 0);
    assert(button(tree, 'DevPulse'));
  });
}

test('fresh mount still initializes the default preset without starting a run', async () => {
  const app = mountApp({ runEffects: true, fetcher: async url => {
    if (url.endsWith('/presets')) return json({ devtool_ebpf: { name: 'DevPulse', description: 'Default', idea: presetIdea } });
    if (url.endsWith('/sessions')) return json([]);
    throw Error(`Unexpected request ${url}`);
  } });
  app.render();
  await flush();
  assert(elements(app.render(), e => e.type === 'input' && e.props.value === presetIdea.title).length);
  assert.equal(app.requests.filter(r => r.options?.method === 'POST').length, 0);
});

test('recovered review visibly labels usage provenance and estimated costs', async () => {
  const session = savedSession();
  session.specialist_reviews = [true, false].map((simulated, i) => ({
    specialist_id: `spec_${i}`, role: `Recovered specialist ${i}`, provider: simulated ? 'mock' : 'openai',
    model: simulated ? 'mock-deterministic' : 'gpt-4o-mini', is_simulated: simulated, status: 'success',
    strengths: [], risks: [], missing_assumptions: [], questions: [], evidence_citations: [],
    invalid_citations: [], assumptions_and_unknowns: [], latency_ms: 50,
    token_usage: { total_tokens: 300 }, cost_estimate_usd: 0.0005,
  }));
  const app = mountApp({ runEffects: true, activeRun: 'saved-run', fetcher: async url => {
    if (url.endsWith('/presets')) return json({});
    if (url.endsWith('/sessions/saved-run')) return json(session);
    if (url.endsWith('/sessions')) return json([]);
    throw Error(`Unexpected request ${url}`);
  } });
  app.render();
  await flush();
  let tree = app.render();
  assert.match(label(tree), /100 reported \/ 200 estimated \/ 300 simulated/);
  assert.match(label(tree), /Est\. cost: \$0\.00100/);
  button(tree, 'Specialist Feedback').props.onClick();
  tree = app.render();
  assert.match(label(tree), /300 tokens \(simulated\)/);
  assert.match(label(tree), /300 tokens \(reported\/estimated\)/);
  assert.match(label(tree), /Est\. cost: \$0\.00050/);
});
