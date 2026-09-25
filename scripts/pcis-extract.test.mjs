import test from 'node:test';
import assert from 'node:assert/strict';
import {validatePcis} from './pcis-extract.mjs';

function example() {
  return {title: 'Permit and Inspection Report Detail', detail: [['Application / Permit', '25010-10000-03188']],
    sections: ['Permit Application Status History', 'Permit Application Clearance Information',
      'Contact Information', 'Inspector Information', 'Pending Inspections', 'Inspection Request History']
      .map(heading => ({heading, tag: 'TABLE', rows: [['No Data Available.']]}))};
}
test('blocks and wrong permit never become a no-data success', () => {
  assert.throws(() => validatePcis({title: 'Forbidden'}, '25010-10000-03188'));
  assert.throws(() => validatePcis(example(), '25010-10000-03189'));
});
test('missing tables fail, explicit no-data is retained', () => {
  const raw = example();
  assert.equal(validatePcis(raw, '25010-10000-03188').sections['Pending Inspections'].source_reports_no_data, true);
  raw.sections.pop();
  assert.throws(() => validatePcis(raw, '25010-10000-03188'));
});
test('partial, conditional and corrected inspections survive unchanged', () => {
  const raw = example();
  raw.sections.at(-1).rows = [
    ['Frame', '7/29/2026', 'Conditional Approval', 'Inspector'],
    ['Frame', '8/1/2026', 'Corrections Issued', 'Inspector'],
    ['Frame', '8/19/2026', 'Approved', 'Inspector'],
  ];
  const result = validatePcis(raw, '25010-10000-03188');
  assert.deepEqual(result.sections['Inspection Request History'].rows, raw.sections.at(-1).rows);
});
