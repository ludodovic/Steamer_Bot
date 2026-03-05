import json
from rapidfuzz import fuzz
from pymongo import ASCENDING, DESCENDING
from datetime import datetime, timedelta
from table2ascii import table2ascii as t2a, PresetStyle

class GestionnaireReservations:

    len_user_name = 10
    len_zone_name = 15

    def __init__(self, db):
        self.db = db
        self.collection = db["ReservationPercepteur"]        
        self.zonelist = []
        config_file = "./souszone_array.json"

        with open(config_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            self.zonelist = data["zonelist"]
    
    def create_reservation(self, user, user_id, zone_id):
        if user != "" and zone_id != "":
            reservation = {
                "user": user,
                "user_id": user_id,
                "date": datetime.now(),
                "exp_date": datetime.now() + timedelta(hours=24),
                "zone": zone_id
            }
        else:
            reservation = None

        return reservation
    
    def try_reservation(self, reservation):
        if reservation is None:
            return None, False
        try:
            user_reservations = self.collection.find({"user_id": reservation["user_id"]})
            nbr_reservations = len(list(user_reservations))
            
            zone_reservations = self.collection.find({"zone": reservation["zone"]})
            zone_reservations_count = len(list(zone_reservations))
        except Exception as e:
            print(f"Error querying reservations: {e}")
            return None, False
        # get the lastest reservation for the zone if it exists
        last_zone_reservation = self.collection.find_one({"zone": reservation["zone"]},sort=[("date", DESCENDING)])
        if last_zone_reservation is not None:
            reservation["exp_date"] = last_zone_reservation["exp_date"] + timedelta(hours=24)

        if nbr_reservations >= 5 or zone_reservations_count >= 5:
            return None, False
        else:
            if self.collection.find_one({"user_id": reservation["user_id"], "zone": reservation["zone"]}) is not None:
                return None, False
            else:
                return reservation["exp_date"], self.collection.insert_one(reservation).acknowledged
    
    def fuzzy_match_zone_by_name(self, query_zone):
        coef = 0
        for zone in self.zonelist:
            score = fuzz.ratio(query_zone, zone)
            if score > coef:
                coef = score
                best_match = zone
        return best_match if coef >= 65 else ""
    
    def get_table_string(self):

        cursor = self.collection.find({}).sort('date', ASCENDING)
        reservation_by_zone = {}

        for resa in cursor:
            if len(resa["user"]) > self.len_user_name:
                user_short = f"{resa['user'][:self.len_user_name]}."
            else:
                user_short = resa["user"]
            if len(resa["zone"]) > self.len_zone_name:
                zone_short = f"{resa['zone'][:self.len_zone_name]}."
            else:                
                zone_short = resa["zone"]
            
            if reservation_by_zone.get(resa["zone"]) is None:
                reservation_by_zone[resa["zone"]] = [zone_short, "|",user_short]
            else:
                reservation_by_zone[resa["zone"]].append(user_short)

        resa_list_len = 4

        reservation_body = []
        for key in reservation_by_zone.keys():
            if len(reservation_by_zone[key]) < resa_list_len:
                while len(reservation_by_zone[key]) < resa_list_len:
                    reservation_by_zone[key].append("---")
            reservation_body.append(reservation_by_zone[key][:resa_list_len])

        output = t2a(
            header = ["Zone", "|","Poseur" ,"En attente"],
            body= reservation_body,
            style = PresetStyle.borderless
        )
        return output
    
    def delete_reservation(self, user_id, zone_name):
        if user_id != "" and zone_name != "":
            result = self.collection.delete_one({"user_id": user_id, "zone": zone_name})
            if result.deleted_count > 0:
                return True, {"user_id": user_id, "zone": zone_name}
        return False, None
    
    def purge_expired_reservations(self, deleted_reservation = None):
        now = datetime.now()
        expired_to_notify = list(self.collection.find({"exp_date": {"$lt": now}}, {"_id": 0, "user_id": 1, "zone": 1}))
        result = self.collection.delete_many({"exp_date": {"$lt": now}})
        next_turn_to_notify = []
        if deleted_reservation is not None:
            next_turn_to_notify.append(self.collection.find_one({"zone": deleted_reservation["zone"]}, {"_id": 0, "user_id": 1, "zone": 1}, sort=[("date", ASCENDING)]))
        for r in expired_to_notify:
            next_turn_to_notify.append(self.collection.find_one({"zone": r["zone"]}, {"_id": 0, "user_id": 1, "zone": 1}, sort=[("date", ASCENDING)]))
        ret = {"deleted_count": result.deleted_count, "to_notify": expired_to_notify, "next_turn": next_turn_to_notify}
        return ret
