import fitbit
from datetime import datetime

class FitbitModule:
    def __init__(self, client_id, client_secret, access_token, refresh_token):
        self.client = fitbit.Fitbit(client_id, client_secret,
                                    access_token=access_token,
                                    refresh_token=refresh_token)
        self.data = {}

    def update(self):
        today = datetime.now().strftime("%Y-%m-%d")
        self.data['steps'] = self.client.activities().get('activities/steps', date=today)['activities-steps'][0]['value']
        self.data['calories'] = self.client.activities().get('activities/calories', date=today)['activities-calories'][0]['value']

    def draw(self, screen):
        # Drawing code here
        pass
