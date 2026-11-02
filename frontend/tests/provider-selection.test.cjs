// Exercise App's real event handlers and request serialization without a DOM.
// The hook harness queues updates until render, matching React's event batching.
const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const jsx = require('react/jsx-runtime');

function mountApp() {
  const state = [];
  const pending = [];
  const requests = [];
  let cursor = 0;
  const hooks = {
    useEffect() {}, // Preset/network initialization is supplied by the fixture.
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
    exports, console, TextDecoder,
    require(name) {
      if (name === 'react') return hooks;
      if (name === 'react/jsx-runtime') return jsx;
      if (name === 'lucide-react') return new Proxy({}, { get: (_, key) => key });
      throw Error(`Unexpected import ${name}`);
    },
    async fetch(url, options) {
      requests.push({ url, options });
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
    return exports.default();
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
    const request = app.requests.filter(r => r.url.endsWith('/run-stream')).at(-1);
    const sentPanel = JSON.parse(request.options.body).panel;
    assert.equal(sentPanel[0].provider, provider);
    assert.equal(sentPanel[0].model, model);
    assert.equal(sentPanel[0].role, 'Specialist 1');
    assert.equal(sentPanel[1].provider, 'mock');
    assert.equal(sentPanel[1].model, 'mock-deterministic');
    tree = app.render();
  }
});
