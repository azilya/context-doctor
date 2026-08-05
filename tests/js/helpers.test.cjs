/** Lightweight Node tests for browser-independent UI helpers. */
const test = require('node:test');
const assert = require('node:assert/strict');
const helpers = require('../../src/context_doctor/static/helpers.js');

test('extracts a rule identifier from rendered result HTML', () => {
    assert.equal(helpers.ruleIdFromHtml('<td>Rule #42: Use SUM</td>'), '42');
});

test('returns null when a result has no rule identifier', () => {
    assert.equal(helpers.ruleIdFromHtml('<pre>No conflicts</pre>'), null);
});
