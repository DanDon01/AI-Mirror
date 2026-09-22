// Offline state regression checks: no browser, network or production fixture.
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const context = vm.createContext({performance: {now: () => 0}});
vm.runInContext(fs.readFileSync(__dirname + '/js/home-twin.js', 'utf8') + ';this.twin=HomeTwin;', context);
const twin = context.twin;
twin.update({watts_now:563,solar_watts:1400,car:{charging:true}},0);
assert.strictEqual(twin.render(), '');
twin.update({watts_now:900,solar_watts:0,battery:{charging:true}},1);
assert.strictEqual(twin.render(), '');
console.log('Home WebGL state regression checks passed');
