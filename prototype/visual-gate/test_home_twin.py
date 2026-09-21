"""Offline regression checks; never load credentials or contact HA."""
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from bridge import Bridge


class HomeTelemetryTests(unittest.TestCase):
    def setUp(self):
        self.bridge = Bridge.__new__(Bridge)
        self.bridge.gate = {}
        self.home = SimpleNamespace(_all_states=[], _states_updated=datetime.now())
        self.bridge.modules = {'smarthome': self.home}

    def entity(self, key, state, **attributes):
        eid = 'test.' + key
        self.bridge.gate[key] = eid
        self.home._all_states.append(dict(entity_id=eid, state=state, attributes=attributes))

    def test_planned_dispatch_does_not_claim_charging(self):
        octo = SimpleNamespace(charge_prefs={}, planned_dispatches=[{'active': True}])
        self.assertIsNone(self.bridge._car(octo))

    def test_real_charging_and_zero_soc(self):
        self.entity('car_charging_entity', 'on')
        self.entity('car_soc_entity', '0')
        self.assertEqual(self.bridge._car(None), {'charging': True, 'charge_pct': 0})

    def test_unknown_is_not_false(self):
        self.entity('car_charging_entity', 'unavailable')
        self.assertIsNone(self.bridge._car(None))

    def test_spatial_states_and_curtain_position(self):
        self.entity('downstairs_temp_entity', '20.4')
        self.entity('upstairs_temp_entity', '19.2')
        self.entity('livingroom_curtain_entity', 'open', current_position=45)
        self.entity('doorbell_motion_entity', 'on')
        self.entity('external_motion_entity', 'off')
        self.entity('livingroom_occupancy_entity', 'on')
        rooms = self.bridge._ha_numbers()['rooms']
        self.assertEqual(rooms['downstairs']['temperature_c'], 20.4)
        self.assertEqual(rooms['upstairs']['temperature_c'], 19.2)
        self.assertEqual(rooms['livingroom']['curtain_position'], 45)
        self.assertTrue(rooms['porch']['occupied'])
        self.assertFalse(rooms['external']['occupied'])
        self.assertNotIn('light', rooms['livingroom'])

    def test_stale_motion_clears(self):
        self.entity('doorbell_motion_entity', 'on')
        self.home._states_updated = datetime.now() - timedelta(seconds=31)
        self.assertNotIn('rooms', self.bridge._ha_numbers())

    def test_home_battery_not_invented(self):
        self.assertNotIn('battery', self.bridge._ha_numbers())


if __name__ == '__main__':
    unittest.main()
