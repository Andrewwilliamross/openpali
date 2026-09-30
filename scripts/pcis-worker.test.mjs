import test from 'node:test';import assert from 'node:assert/strict';
import {permitUrl,runWorker} from './pcis-worker.mjs';
test('only permit identifiers can form a browser URL',()=>{assert.match(permitUrl('25010-10000-03188'),/id1=25010&id2=10000&id3=03188$/);assert.throws(()=>permitUrl('../admin'));});
test('oversized and invalid jobs fail before opening a browser',async()=>{await assert.rejects(runWorker({},Array(26).fill({permit:'25010-10000-03188',apn:'4412013017'}),'/tmp/unused'));await assert.rejects(runWorker({},[{permit:'25010-10000-03188',apn:'oops'}],'/tmp/unused'));});
