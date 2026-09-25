import {describe,it,expect} from 'vitest';
import {apiPath,money,stages} from './api';
describe('public presentation boundaries',()=>{
 it('never labels missing price as zero',()=>{expect(money(null)).toBe('Not recorded');expect(money(2095000)).toBe('$2,095,000')});
 it('distinguishes reported construction completion from occupancy',()=>{expect(stages.construction_complete.label).not.toMatch(/occupancy/i);expect(stages.unknown.label).not.toMatch(/uncleared|vacant|undamaged/i)});
 it('pins requests to one release',()=>{expect(apiPath('evidence-a','properties/123')).toBe('/v1/evidence/releases/evidence-a/properties/123')});
});
