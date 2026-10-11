// Offline state regression checks: no browser, network or production fixture.
const fs = require('fs'), vm = require('vm'), path = require('path'), assert = require('assert');
// The house pack's renderer when present (as the server serves it), else the example.
const pack = process.env.MIRROR_HOUSE_DIR ? path.resolve(process.env.MIRROR_HOUSE_DIR) : path.resolve(__dirname, '..', '..', 'house');
const own = path.join(pack, 'visual-gate', 'js', 'home-twin.js');
const renderer = fs.existsSync(own) ? own : path.join(__dirname, 'js', 'home-twin.js');
const context = vm.createContext({performance: {now: () => 0}});
vm.runInContext(fs.readFileSync(renderer, 'utf8') + ';this.twin=HomeTwin;', context);
const twin = context.twin;
twin.update({watts_now:563,solar_watts:1400,car:{charging:true}},0);
assert.strictEqual(twin.render(), '');
twin.update({watts_now:900,solar_watts:0,battery:{charging:true}},1);
assert.strictEqual(twin.render(), '');
console.log('Home WebGL state regression checks passed');
