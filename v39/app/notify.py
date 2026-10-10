"""Beständig kö till Power Automate. 202 betyder mottaget, inte färdigbehandlat."""
import json
import logging
import os
import sqlite3
import threading
import time
from contextlib import closing
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

DATABASE = os.environ.get('NOTIFY_DATABASE', '/var/lib/novatrix-api/notifications.db')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def database():
    connection = sqlite3.connect(DATABASE, timeout=10)
    connection.execute('CREATE TABLE IF NOT EXISTS notifications '
                       '(id TEXT PRIMARY KEY, payload TEXT NOT NULL, accepted INTEGER NOT NULL DEFAULT 0)')
    return connection


def enqueue(record):
    with closing(database()) as connection, connection:
        connection.execute('INSERT OR IGNORE INTO notifications (id,payload) VALUES (?,?)',
                           (record['id'], json.dumps({'schemaVersion': '1.0', **record})))


def dispatch():
    url = os.environ.get('POWER_AUTOMATE_URL', '')
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.fragment:
        raise RuntimeError('En giltig HTTPS-adress till Power Automate krävs.')
    if not parsed.hostname or not parsed.hostname.endswith('.environment.api.powerplatform.com'):
        raise RuntimeError('Anropsadressen måste tillhöra Power Automates miljödomän.')
    opener = build_opener(NoRedirect())
    while True:
        try:
            with closing(database()) as connection, connection:
                rows = connection.execute('SELECT id,payload FROM notifications WHERE accepted=0 LIMIT 10').fetchall()
            for ticket, payload in rows:
                try:
                    request = Request(url, data=payload.encode('utf-8'),
                                      headers={'Content-Type': 'application/json; charset=utf-8'}, method='POST')
                    with opener.open(request, timeout=30) as response:
                        status = response.status
                    if status != 202:
                        raise RuntimeError('Oväntat svar från flödet.')
                    with closing(database()) as connection, connection:
                        connection.execute('UPDATE notifications SET accepted=1 WHERE id=?', (ticket,))
                    logging.info('Flödet har tagit emot ärende %s', ticket)
                except Exception:
                    # Undvik undantagstext som kan innehålla den hemliga anropsadressen.
                    logging.warning('Notisanropet kunde inte bekräftas för %s; nytt försök senare', ticket)
        except Exception:
            logging.error('Notiskön kunde inte läsas; nytt försök senare')
        time.sleep(15)


def start_worker():
    database().close()
    threading.Thread(target=dispatch, daemon=True).start()
