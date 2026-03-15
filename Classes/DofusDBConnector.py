import requests
import json

class DofusDBConnector:
    def __init__(self, base_url):
        self.base_url = base_url

    def get_item(self, route, limit=10, skip=0):
        try:
            url = f"{self.base_url}/{route}?$skip={skip}&$limit={limit}"
            response = requests.get(url)
            if response.status_code == 200:
                return response.json()
            else:
                raise Exception(f"Failed to fetch item with ID {route}: {response.status_code}")
        except Exception as e:
            print(f"Error fetching item with ID {route}: {e}")
            return None
        
    def get_subzone_dict(self):
        subzone_list = {}
        while True:
            try:
                subzones = self.get_item("subareas", limit=10, skip=len(subzone_list))
                if len(subzones["data"]) == 0:
                    break
                for sz in subzones["data"]:
                    subzone_list[sz["id"]] = sz["name"]["fr"]
            except Exception as e:
                print(f"Error fetching subzones: {e}")
                break
        return subzone_list
    
    def get_dungeon_dict(self):
        dungeon_dict = {}
        while True:
            try:
                dungeons = self.get_item("dungeons", limit=10, skip=len(dungeon_dict))
                if len(dungeons["data"]) == 0:
                    break
                for d in dungeons["data"]:
                    dungeon_dict[d["subarea"]] = d["entranceMapId"]
            except Exception as e:
                print(f"Error fetching dungeons: {e}")
                break
        return dungeon_dict
    
    def get_zone_list(self):
        dungeon_dict = self.get_dungeon_dict()
        zone_dict = self.get_subzone_dict()

        linked_dungeons = []

        for dungeon_id, entrance_map_id in dungeon_dict.items():
            url = f"{self.base_url}/subareas?mapIds[$in][]={entrance_map_id}"
            sub_zone_id = None
            dungeon_zone_id = dungeon_id
            try:
                response = requests.get(url)
                if response.status_code == 200:
                    sub_zone_id = response.json()["data"][0]["id"] if response.json()["data"] else None
                    linked_dungeons.append((dungeon_zone_id, sub_zone_id))
                else:
                    raise Exception(f"Failed to fetch item with ID subareas: {response.status_code}")
            except Exception as e:
                print(f"Error fetching item with ID subareas: {e}")
                return None
        
        def is_relevant_zone(zone_name):
            irrelevant_keywords = ["Bonta - étage", "Brâkmar - étage", "Expédition - ", "Expédition de", "Hall de guilde"]
            return not any(keyword in zone_name for keyword in irrelevant_keywords)
        
        linked_zone_list = {}
        for key, value in zone_dict.items():
            if is_relevant_zone(value):
                linked_zone_list[value] = value

        for dungeon_zone_id, sub_zone_id in linked_dungeons:
            subzone_name = zone_dict.get(sub_zone_id, None)
            dungeon_name = zone_dict.get(dungeon_zone_id, None)
            if subzone_name and dungeon_name:
                subzone_alias = f"[DJ] {subzone_name}"
                linked_zone_list[subzone_name] = subzone_alias
                linked_zone_list[dungeon_name] = subzone_alias
            else:
                print(f"Warning: Could not find names for dungeon_zone_id {dungeon_zone_id}:\"{dungeon_name}\" or sub_zone_id {sub_zone_id}:\"{subzone_name}\"")

        return linked_zone_list