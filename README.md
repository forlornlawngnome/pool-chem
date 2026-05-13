# Salt Water Pool Chemistry Advisor

A TFP PoolMath-based salt water pool chemistry calculator with dosage recommendations and test history, running as a Docker container.

## Quick start (after pushing to GitHub)

Edit `docker-compose.yml` and replace the image name with your GitHub username and repo, then:

```bash
docker compose up -d
```

Open http://localhost:5000 in your browser.

## Setup from scratch

1. Create a new GitHub repo (e.g. `pool-chem`)
2. Push this directory to it:
   ```bash
   git init
   git add .
   git commit -m "initial commit"
   git remote add origin https://github.com/YOUR_USERNAME/pool-chem.git
   git branch -M main
   git push -u origin main
   ```
3. GitHub Actions will build and push the image to GHCR automatically
4. Make the package public: repo → Packages → package settings → visibility → Public
5. Update `docker-compose.yml` with your username/repo and run `docker compose up -d`

## Notes

- History is stored in the browser's localStorage — it persists between visits on the same browser
- No backend database needed; the app is fully stateless
- To update: push changes to GitHub, then `docker compose pull && docker compose up -d`
