import json
from rapidfuzz import fuzz
from pymongo import ASCENDING, DESCENDING
from datetime import datetime, timedelta
from table2ascii import table2ascii as t2a, PresetStyle

class GestionnaireReservations:
    def __init__(self, db):
        self.db = db
        self.collection = db["ReservationPercepteur"]        
        self.zonelist = []
        config_file = "./zone.json"

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
        self.purge_expired_reservations()
        if reservation is None:
            return False
        try:
            user_reservations = self.collection.find({"user_id": reservation["user_id"]})
            nbr_reservations = len(list(user_reservations))
            
            zone_reservations = self.collection.find({"zone": reservation["zone"]})
            zone_reservations_count = len(list(zone_reservations))
        except Exception as e:
            print(f"Error querying reservations: {e}")
            return False
        # get the lastest reservation for the zone if it exists
        last_zone_reservation = self.collection.find_one({"zone": reservation["zone"]},sort=[("date", DESCENDING)])
        if last_zone_reservation is not None:
            reservation["exp_date"] = last_zone_reservation["exp_date"] + timedelta(hours=24)

        if nbr_reservations >= 3 or zone_reservations_count >= 5:
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
        self.purge_expired_reservations()

        cursor = self.collection.find({}).sort('date', ASCENDING)
        reservation_by_zone = {}

        for resa in cursor:
            if reservation_by_zone.get(resa["zone"]) is None:
                reservation_by_zone[resa["zone"]] = [resa["zone"], "|",resa["user"]]
            else:
                reservation_by_zone[resa["zone"]].append(resa["user"])

        reservation_body = []
        for key in reservation_by_zone.keys():
            if len(reservation_by_zone[key]) < 7:
                while len(reservation_by_zone[key]) < 7:
                    reservation_by_zone[key].append("---")
            reservation_body.append(reservation_by_zone[key])

        output = t2a(
            header = ["Zone", "|","Droit de pose" ,"En attente n°1" ,"En attente n°2", "En attente n°3", "En attente n°4"],
            body= reservation_body,
            style = PresetStyle.thin_compact
        )
        return output
    
    def delete_reservation(self, user_id, zone_name):
        self.purge_expired_reservations()
        if user_id != "" and zone_name != "":
            result = self.collection.delete_one({"user_id": user_id, "zone": zone_name})
            return result.deleted_count > 0
        return False
    
    def purge_expired_reservations(self):
        now = datetime.now()
        result = self.collection.delete_many({"exp_date": {"$lt": now}})
        return result.deleted_count