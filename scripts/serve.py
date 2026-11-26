"""Start the existing app with paths resolved from this checkout (including after a move)."""
import argparse
import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
from waitress import serve


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['local', 'public'], default='local')
    parser.add_argument('--port', type=int)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    load_dotenv(root / '.env', override=False)
    if args.mode == 'public':
        config = root / 'instance' / 'docker_demo.env'
        if not config.is_file():
            raise SystemExit('Missing instance/docker_demo.env for public deployment')
        load_dotenv(config, override=True)
        hosts = [h.strip() for h in os.getenv('PUBLIC_HOSTS', '').split(',') if h.strip()]
        hosts.append('foodlens-demo.foodlens-anthen-demo.workers.dev')
        origin_file = root / 'instance' / 'tunnel_origin.txt'
        if origin_file.is_file():
            origin = urlsplit(origin_file.read_text(encoding='utf-8-sig').strip())
            if origin.scheme != 'https' or not (origin.hostname or '').endswith('.trycloudflare.com'):
                raise SystemExit('Invalid tunnel origin; verify instance/tunnel_origin.txt')
            hosts.append(origin.hostname)
        os.environ['PUBLIC_HOSTS'] = ','.join(dict.fromkeys(hosts))
        database = root / 'instance' / 'demo_tunnel.sqlite3'
    else:
        database = root / 'instance' / 'food_reviews.sqlite3'
    if not database.is_file():
        raise SystemExit('Existing database not found; refusing to create an empty replacement')
    os.environ['DEPLOYMENT_MODE'] = args.mode
    os.environ['DATABASE_PATH'] = str(database)
    os.environ['MODEL_PATH'] = str(root / 'outputs' / 'baseline.joblib')
    os.environ['RETRIEVAL_METHOD'] = 'bm25'
    os.environ['AUTO_BUILD_DENSE'] = '0'
    from webapp import create_app
    serve(create_app(), host='127.0.0.1', port=args.port or (5000 if args.mode == 'public' else 5001), threads=4)


if __name__ == '__main__':
    main()
