import os
import json
import time
import requests
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

HP_URL = os.getenv("HP_URL")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
HISTORY_FILE = "grades_history.json"
CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL_SECONDS", 3600))
HEADLESS_MODE = os.getenv("HEADLESS_MODE", "True").lower() == "true"

class HyperplanningBot:
    def __init__(self):
        self.ensure_auth_file()
        self.seen_grades = self.load_history()

    def ensure_auth_file(self):
        auth_path = "auth_state.json"
        auth_env = os.getenv("AUTH_STATE_JSON")
        
        if not os.path.exists(auth_path):
            if auth_env:
                print("Création du fichier auth_state.json à partir de la variable d'environnement...")
                try:
                    with open(auth_path, "w", encoding="utf-8") as f:
                        f.write(auth_env)
                except Exception as e:
                    print(f"Erreur lors de l'écriture du fichier auth : {e}")
            else:
                print("Attention : Pas de fichier auth_state.json ni de variable AUTH_STATE_JSON.")

    def load_history(self):
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except json.JSONDecodeError:
                return []
        return []

    def save_history(self):
        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.seen_grades, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Erreur sauvegarde historique: {e}")

    def send_discord_notification(self, grade_info):
        try:
            grade_str = grade_info['grade'].replace(',', '.')
            if '/' in grade_str:
                numerator, denominator = grade_str.split('/')
                val = (float(numerator) / float(denominator)) * 20
            else:
                val = float(grade_str)
            
            GREEN = 3066993
            ORANGE = 15105570
            RED = 15158332
            
            if val >= 10:
                color = GREEN
            elif val >= 8:
                color = ORANGE
            else:
                color = RED
        except Exception as e:
            print(f"Erreur calcul couleur: {e}")
            color = 3066993

        embed = {
            "title": "Nouvelle Note Détectée ! 🎓",
            "color": color,
            "fields": [
                {"name": "Matière", "value": grade_info['subject'], "inline": True},
                {"name": "Note", "value": grade_info['grade'], "inline": True},
                {"name": "Date", "value": grade_info['date'], "inline": True}
            ],
            "footer": {"text": "Hyperplanning Bot - INSA"}
        }
        data = {
            "username": "HyperPlanning Bot",
            "embeds": [embed]
        }
        try:
            requests.post(DISCORD_WEBHOOK_URL, json=data)
            print(f"Notification envoyée pour {grade_info['subject']}")
        except Exception as e:
            print(f"Erreur lors de l'envoi Discord : {e}")

    def run(self):
        auth_path = "auth_state.json"
        
        if not os.path.exists(auth_path):
            print("Erreur: Fichier d'authentification introuvable.")
            print("Veuillez configurer la variable AUTH_STATE_JSON dans Portainer.")
            return

        with sync_playwright() as p:
            print(f"Lancement navigateur (Headless: {HEADLESS_MODE})...")
            browser = p.chromium.launch(headless=HEADLESS_MODE)
            try:
                context = browser.new_context(storage_state=auth_path)
            except Exception as e:
                print(f"Erreur chargement session: {e}.")
                browser.close()
                return

            page = context.new_page()
            
            print("Connexion à Hyperplanning...")
            try:
                page.goto(HP_URL, timeout=60000)
                
                try:
                    page.wait_for_selector('section.notes', timeout=30000)
                    print("Widget 'Dernières notes' détecté.")
                except:
                    print("Timeout: Widget non trouvé.")
                
                parsed_grades = []
                items = page.locator("section.notes ul.liste-clickable li").all()
                print(f"Extraction : {len(items)} notes trouvées.")
                
                for item in items:
                    try:
                        subject = item.locator("h3 span").inner_text().strip()
                        date = item.locator(".date").inner_text().strip()
                        grade_locator = item.locator(".as-info.fixed")
                        grade_text = grade_locator.inner_text().strip().replace('\n', '')
                        
                        grade_obj = {
                            "subject": subject,
                            "date": date,
                            "grade": grade_text
                        }
                        parsed_grades.append(grade_obj)
                    except Exception as e:
                        pass # Ignorer les erreurs de parsing individuelles

                new_grades_count = 0
                self.seen_grades = self.load_history()

                for grade in reversed(parsed_grades):
                    is_known = False
                    for known in self.seen_grades:
                        if known['subject'].strip() == grade['subject'].strip() and \
                           known['date'].strip() == grade['date'].strip() and \
                           known['grade'].strip() == grade['grade'].strip():
                            is_known = True
                            break
                    
                    if not is_known:
                        print(f"Nouvelle note : {grade['subject']} ({grade['grade']})")
                        self.send_discord_notification(grade)
                        self.seen_grades.append(grade)
                        new_grades_count += 1
                
                if new_grades_count > 0:
                    self.save_history()
                    print(f"{new_grades_count} notifications envoyées.")
                else:
                    print("Aucune nouvelle note.")

            except Exception as e:
                print(f"Erreur pendant la navigation: {e}")
            finally:
                browser.close()

if __name__ == "__main__":
    if not HP_URL or not DISCORD_WEBHOOK_URL:
        print("ERREUR: HP_URL ou DISCORD_WEBHOOK_URL manquant.")
    else:
        bot = HyperplanningBot()
        print(f"Démarrage du bot RPi (Intervalle: {CHECK_INTERVAL_SECONDS}s)")
        
        while True:
            try:
                bot.run()
            except Exception as e:
                print(f"Erreur critique lors de l'exécution : {e}")
            
            print(f"Mise en veille pour {CHECK_INTERVAL_SECONDS} secondes...")
            time.sleep(CHECK_INTERVAL_SECONDS)
