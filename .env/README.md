# `.env/` Agent Secret Keys Folder

All 18 agents in `career_agent_system.py` automatically load secrets from this folder on startup via `live/env_loader.py`.

## 3 Ways to Store Keys Here
1. **Edit `.env/secrets.env`**: Standard `KEY=VALUE` lines.
2. **Edit `.env/keys.json`**: Structured JSON object.
3. **CLI Command**: Run `python3 career_agent_system.py --set-key KEY=VALUE` or drop a single-key file `.env/<KEY_NAME>`.

## Check Loaded Keys
```bash
python3 career_agent_system.py --mode check-env
```
