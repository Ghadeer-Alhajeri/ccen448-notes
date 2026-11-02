# Gadeer's Notes

A small dynamic notes website for CCEN448 Lab 6, created with AI assistance.
Register an account, log in, and create or delete notes. Accounts and notes
are stored in PostgreSQL. Each user can access only their own notes.

## Components

- Flask handles registration, login, sessions, and note requests on the server.
- Werkzeug stores salted password hashes rather than plaintext passwords.
- Flask-WTF protects forms against CSRF. Jinja escapes user-provided content.
- Gunicorn serves the application on port 8000.
- PostgreSQL 17 runs in a separate container on the same Lightsail instance.
- A Docker volume retains database records across container restarts.
- PostgreSQL is not exposed through a host port.

## Deploy on the Ubuntu Lightsail instance

This repository does not create AWS resources. Use the supplied lab OpenTofu
template to create the instance and clone this public repository to /opt/website.
Use an Ubuntu LTS instance and allow TCP 8000 during the direct HTTP part.
Install Docker Engine and the Docker Compose plugin using Docker's Ubuntu
instructions: https://docs.docker.com/engine/install/ubuntu/.
If using Ubuntu's docker.io and docker-compose-v2 packages instead, confirm
that `sudo docker compose version` succeeds before continuing.

Run these commands on the instance after cloud-init finishes:

```bash
cd /opt/website
python3 setup_env.py
sudo docker compose up -d --build
sudo docker compose ps
curl --fail http://127.0.0.1:8000/health
```

Open http://YOUR_STATIC_IPV4:8000/register in your browser. Use a new lab-only
password of at least 10 characters. Create a note, log out, log in, and check
that your note remains. Create a second user to demonstrate account isolation.
This is a teaching application, not a hardened public production service;
it does not include password recovery or login rate limiting.

## Show the database for the report

Show running services with `sudo docker compose ps`, or connect to PostgreSQL:

```bash
sudo docker compose exec db psql -U notes -d notes
```

Inside psql:

```sql
\dt
SELECT id, username FROM "user";
SELECT id, user_id, title, created_at FROM note;
\q
```

Do not display password hashes or .env secrets in screenshots.

## Cloudflare Quick Tunnel using your Mac

Keep the following SSH command running on your Mac, replacing the IP:

```bash
ssh -i ~/Downloads/gadeer-key-ccen448f26.pem -N -L 127.0.0.1:8080:localhost:8000 ubuntu@YOUR_STATIC_IPV4
```

In another Mac terminal:

```bash
cloudflared tunnel --url http://127.0.0.1:8080
```

Open the printed HTTPS URL and log in again. A new hostname has its own
cookies; accounts and notes are still in the same database. All links and forms
are relative, so no fixed public URL or trusted forwarded headers are required.

After verifying HTTPS access, set public_http = false in the OpenTofu template
and apply it. The Lightsail firewall should then have only SSH (22) open.
Also restrict Docker's published web port to loopback on the instance. This
prevents Docker's published port being reachable through an unintended route:

```bash
cd /opt/website
sed -i 's/^WEB_BIND=.*/WEB_BIND=127.0.0.1/' .env
sed -i 's/^COOKIE_SECURE=.*/COOKIE_SECURE=true/' .env
sudo docker compose up -d --force-recreate web
```

Secure cookies work with the browser's HTTPS connection even though the
Cloudflare-to-origin leg uses HTTP. Log in again if necessary. Do not enable
secure cookies during the initial direct HTTP demonstration. Do not publish
or screenshot .env. If you need to return to direct HTTP, restore
WEB_BIND=0.0.0.0 and COOKIE_SECURE=false, recreate web, and reopen the web
firewall rule through OpenTofu.

## Stop and clean up

`sudo docker compose down` stops the containers and retains database data.
`sudo docker compose down -v` also deletes the database volume permanently.
At the end of the lab, stop both Mac tunnel processes, run `tofu destroy`
from the OpenTofu folder on your Mac, and delete the lab SSH keys and IAM
resources as directed by the lab. Destroying the instance deletes its local
database data too. Do not delete any unrelated pre-existing keys or resources.

## Development checks

With Python 3.12:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt pytest==8.4.2
python -m pytest -q
```

Unit tests use a temporary SQLite database to check application behavior.
The actual deployment uses PostgreSQL. A successful unit test run does not
verify Docker images, the AWS deployment, or the Cloudflare tunnel; verify
those on the live instance using the commands above.
