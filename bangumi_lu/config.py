import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    def __init__(self):
        base_url = "https://api.bgm.tv"
        self.timeout = 20
        self.token = os.getenv('BANGUMI_TOKEN')
        self.user_url = base_url + "/v0/me"
        self.collection_url = base_url + "/v0/users/{username}/collections"
        self.subject_character_url = base_url + "/v0/subjects/{subject_id}/characters"
        self.character_url = base_url + "/v0/characters/{character_id}"
