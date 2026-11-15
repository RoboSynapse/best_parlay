// Run: node web/model.test.mjs
import assert from 'node:assert/strict';
import { toDecimal, kelly } from './model.js';

const near = (a, b) => assert.ok(Math.abs(a - b) < 1e-4, `${a} != ${b}`);
near(toDecimal('1.85'), 1.85);
near(toDecimal('1,85'), 1.85);
near(toDecimal('+150'), 2.5);
near(toDecimal('-120'), 1.8333);
near(toDecimal('−120'), 1.8333);
near(toDecimal('-200'), 1.5);
near(toDecimal('101.0'), 101);  // long-shot decimal odds stay decimal
assert.ok(Number.isNaN(toDecimal('')));
near(kelly(0.5, 2.5), 0.25 / 1.5);  // (p·o − 1) / (o − 1)
assert.equal(kelly(0.4, 2.0), 0);    // no edge -> no stake
assert.equal(kelly(0.5, 1), 0);      // invalid odds
console.log('model.test.mjs: ok');
