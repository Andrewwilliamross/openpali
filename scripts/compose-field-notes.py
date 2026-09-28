#!/usr/bin/env python3
"""Compose the editable flat field drawing from the original rig and County lines."""
from pathlib import Path
import copy
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
BRAND = ROOT / 'assets/brand/field-notes-2d'
ET.register_namespace('', 'http://www.w3.org/2000/svg')
NS = '{http://www.w3.org/2000/svg}'

def compose():
    map_svg = ET.parse(BRAND / 'map/close/alphabet-streets-linework.svg').getroot()
    map_parts = []
    for child in map_svg:
        if child.tag == NS+'defs' or child.get('id') in ('actual-parcels', 'actual-street-centerlines', 'verified-street-labels'):
            child = copy.deepcopy(child)
            if child.get('id') == 'actual-parcels':
                child.set('stroke', '#7196db')
                child.set('opacity', '.8')
                child.set('stroke-width', '1.3')
            if child.get('id') == 'verified-street-labels':
                child.set('font-family', 'DM Sans,Arial,sans-serif')
                child.set('font-size', '12')
                child.set('letter-spacing', '1')
            map_parts.append(ET.tostring(child, encoding='unicode'))
    rig = ET.parse(BRAND / 'pelican.svg').getroot()
    rig_parts = []
    for child in rig:
        if child.tag == NS+'style':
            # Inline rig styles are scoped to the character to avoid document collisions.
            css = child.text.split('#left-foot')[0]
            for selector in ('.ink{', '.fine{', '.paper{', '.blue{', '.ink-fill{'):
                css = css.replace(selector, '#pelican '+selector)
            rig_parts.append('<style>'+css+'</style>')
        elif child.get('id') in ('left-foot', 'right-foot'):
            rig_parts.append(ET.tostring(child, encoding='unicode'))
    rig_parts.append('<g id="upper-body">')
    for child in rig:
        if child.get('id') in ('body', 'head', 'notebook', 'pencil', 'wing'):
            rig_parts.append(ET.tostring(child, encoding='unicode'))
    rig_parts.append('</g>')
    artwork = '''<svg xmlns="http://www.w3.org/2000/svg" id="field-scene" class="field-scene" viewBox="0 0 1100 850" role="img" aria-labelledby="scene-title scene-description">
<title id="scene-title">A pelican at work on the Palisades field drawing</title>
<desc id="scene-description">A flat ink drawing of actual parcels around Galloway Street, Hartzell Street, and Bestor Boulevard. A white and blue pelican carries a field notebook, waddles across the page, inspects the drawing, and underlines a margin note with its pencil. A separate architectural sketch is illustrative.</desc>
<rect width="1100" height="850" fill="white"/>
<g class="plan-label" font-family="Arial,sans-serif" fill="#577299">
 <text x="49" y="34" font-size="11" letter-spacing="2">PACIFIC PALISADES</text>
 <text x="49" y="61" font-size="21" fill="#1557ff">The Alphabet Streets</text>
 <text x="760" y="26" font-size="10" text-anchor="middle">N</text>
 <path d="M760 69V38m-6 9 6-10 6 10" fill="none" stroke="#1557ff" stroke-width="1.2"/>
</g>
<g class="map-base">MAP_PARTS</g>
<g fill="none" stroke="#a8bde1" stroke-width="1">
 <path d="M35 108V78h30m696 0h30v30M35 619v30h30m696 0h30v-30"/>
 <path d="M819 79v558" stroke-dasharray="2 6"/>
</g>
<g id="illustrative-details" font-family="Arial,sans-serif">
 <text x="856" y="110" fill="#1557ff" font-size="12" letter-spacing="2">IN THE MARGIN</text>
 <text x="856" y="134" fill="#6e809a" font-size="10">An architectural drawing study</text>
 <g fill="none" stroke="#6e91cd" stroke-width="1.4" stroke-linejoin="round">
  <path d="M864 187h178v159h-66m-32 0h-80V187m8 8h162v143h-58m-32 0h-72V195"/>
  <path d="M966 195v65m0 32v46M872 279h94m0 0h68m-90 59v-32a32 32 0 0 1 32 32m-10-78h32a32 32 0 0 1-32 32"/>
  <path d="M896 187h49m-49 8h49m66 84v-61h-28v61m0-48h28m-28 10h28m-28 10h28m-28 10h28m-128 47h36v18h-36z"/>
  <path d="M854 164h198m-187-9v22m178-22v22m-183-8 10-10m168 10 10-10M1060 182v169m-8-163h18m-18 158h18m-15-153 10-10m-10 168 10-10" stroke="#b4c7e7"/>
  <path d="M884 202v64m5-64v64m-5-61 5-3m-5 17 5-3m-5 17 5-3m-5 17 5-3m-5 17 5-3" stroke="#a4bce0"/>
 </g>
 <text x="864" y="376" font-size="9" letter-spacing="1.4" fill="#6e809a">PLAN STUDY · ILLUSTRATIVE</text>
 <g fill="none" stroke="#6e91cd" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">
  <path d="M853 498h201M866 493v-47l86-45 88 45v47M872 493v-43l80-42 82 42v43M866 455h174m-174 4h174M897 459v34m62-34v34m-52 0v-24h40v24m32-25h36v15h-36z"/>
  <path d="m877 501-6 7m23-7-6 7m23-7-6 7m23-7-6 7m23-7-6 7m23-7-6 7m23-7-6 7m23-7-6 7m23-7-6 7m23-7-6 7" stroke="#b4c7e7"/>
 </g>
 <text x="864" y="535" font-size="9" letter-spacing="1.4" fill="#6e809a">ELEVATION STUDY</text>
 <text x="864" y="574" font-size="10" fill="#6e809a">A study of drawing.</text>
 <text x="864" y="591" font-size="10" fill="#6e809a">No building proposal is shown.</text>
</g>
<g id="margin-note">
 <text x="763" y="665" class="pencil-text" font-family="Georgia,serif" font-style="italic" font-size="23" fill="#1557ff">Source first.</text>
 <path class="annotation-rest" d="M769.9 690.45C781 687 792 694 805.9 690.45" fill="none" stroke="#b4c7eb" stroke-width="1.8" stroke-linecap="round"/>
 <path id="pencil-stroke" class="annotation-ink" d="M769.9 690.45C781 687 792 694 805.9 690.45" fill="none" stroke="#1557ff" stroke-width="2" stroke-linecap="round" pathLength="1"/>
 <path d="M763 715h231m-231 22h188" fill="none" stroke="#e0e8f5" stroke-width="1"/>
 <text x="763" y="773" class="plan-label" font-family="Arial,sans-serif" font-size="10" fill="#64748a" letter-spacing="1.1">THEN THE STORY.</text>
</g>
<g opacity="0" class="selected-note" id="source-emphasis" fill="none" stroke="#1557ff" stroke-width="1.5"><path d="M851 121h170M49 52h90"/></g>
<g opacity="0" class="selected-note" id="dates-emphasis" fill="none" stroke="#1557ff" stroke-width="1.5"><path d="M765 715h225"/></g>
<g opacity="0" class="selected-note" id="correction-emphasis" fill="none" stroke="#1557ff" stroke-width="1.5"><path d="M765 737h183"/></g>
<g id="pelican-position" transform="translate(140.1 499.8)">
 <g id="pelican-facing"><g id="pelican" transform="scale(1.23)">RIG_PARTS</g></g>
</g>
<g font-family="Arial,sans-serif" fill="#6b80a0" font-size="9" class="scene-attribution">
 <text x="49" y="835">PARCELS: LA COUNTY ASSESSOR · STREETS: LA COUNTY CAMS</text>
 <text x="1053" y="835" text-anchor="end" letter-spacing="1">FIELD NOTES / 01</text>
</g>
</svg>'''.replace('MAP_PARTS', '\n'.join(map_parts)).replace('RIG_PARTS', '\n'.join(rig_parts))
    (BRAND / 'scene.svg').write_text(artwork)
    return artwork

if __name__ == '__main__':
    compose()
    print('Composed assets/brand/field-notes-2d/scene.svg')
