/** Read-only DOM adapter for an already-open public LADBS PCIS detail page.
 * Works with a Playwright Page, or with cua Tab.playwright as the argument.
 * Navigation/worker scheduling are deliberately caller responsibilities.
 */
export function readPcisDom() {
  return {
    title: document.title,
    detail: Array.from(document.querySelectorAll('dt')).map(dt => [
      dt.innerText.trim(), dt.nextElementSibling?.innerText.trim(),
    ]),
    sections: Array.from(document.querySelectorAll('h3')).map(h => ({
      heading: h.innerText.trim(),
      tag: h.nextElementSibling?.tagName,
      rows: Array.from(h.nextElementSibling?.querySelectorAll('tr') || []).map(tr =>
        Array.from(tr.querySelectorAll('td,th')).map(td => td.innerText.trim())),
    })),
  };
}

const TABLES = {
  'Permit Application Status History': 3,
  'Permit Application Clearance Information': 4,
  'Contact Information': 3,
  'Inspector Information': 2,
  'Pending Inspections': null,
  'Inspection Request History': 4,
};

export function validatePcis(raw, permit) {
  if (!/^\d{5}-\d{5}-\d{5}$/.test(permit)) throw new Error('Invalid permit ID');
  if (raw?.title !== 'Permit and Inspection Report Detail') throw new Error('Unexpected page or access block');
  if (!Array.isArray(raw.detail) || !Array.isArray(raw.sections)
      || raw.detail.some(row => row.length !== 2 || row.some(value => typeof value !== 'string'))
      || new Set(raw.detail.map(row => row[0])).size !== raw.detail.length) {
    throw new Error('Missing, malformed or ambiguous permit details');
  }
  const details = Object.fromEntries(raw.detail);
  if (details['Application / Permit'] !== permit) throw new Error('Wrong permit page');
  const sections = {};
  for (const [heading, width] of Object.entries(TABLES)) {
    const matches = raw.sections.filter(s => s.heading === heading);
    if (matches.length !== 1 || matches[0].tag !== 'TABLE') throw new Error(`Missing or changed section: ${heading}`);
    const rows = matches[0].rows;
    const explicitEmpty = rows.length === 1 && rows[0].length === 1 && rows[0][0] === 'No Data Available.';
    if (!explicitEmpty && (!rows.length || rows.some(r => width && r.length !== width))) {
      throw new Error(`Unexpected table shape: ${heading}`);
    }
    sections[heading] = {source_reports_no_data: explicitEmpty, rows: explicitEmpty ? [] : rows};
  }
  // Preserve all outcomes verbatim. Conditional/partial approvals, corrections,
  // and requests are not full approvals or precise trade start/finish dates.
  return {schema_version: 'pcis-dom-v1', permit, details, sections};
}

export async function extractPcis(page, permit) {
  const raw = await page.evaluate(readPcisDom);
  return {observed_at: new Date().toISOString(), raw, parsed: validatePcis(raw, permit)};
}
