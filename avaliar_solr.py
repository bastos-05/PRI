#!/usr/bin/env python3
"""Avaliação manual de resultados Solr numa interface local, sem dependências."""

import argparse
import csv
import html
import io
import json
import re
import secrets
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen

SOLR = "http://localhost:8983/solr/pri/select"


def save(path, session):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(session, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def fetch(endpoint, original, top):
    payload = {**original, "fields": "id,title,text", "limit": top}
    req = Request(endpoint, data=json.dumps(payload).encode("utf-8"),
                  headers={"Content-Type": "application/json", "Accept": "application/json"},
                  method="POST")
    try:
        with urlopen(req, timeout=90) as response:
            docs = json.load(response)["response"]["docs"]
    except HTTPError as err:
        raise ValueError(f"Solr HTTP {err.code}: {err.read().decode(errors='replace')}") from err
    return docs[:top]


def make_session(runs, endpoint, selected, top):
    queries, articles, rankings = {}, {}, []
    names = set()
    for spec in runs:
        name, sep, source = spec.partition("=")
        name = name.strip()
        if not sep or not name or not source or name in names:
            raise ValueError(f"Configuração inválida ou repetida: {spec!r}. Usa NOME=caminho.")
        names.add(name)
        src = Path(source).expanduser()
        files = sorted(src.glob("*.json")) if src.is_dir() else [src]
        matched, seen = 0, set()
        for path in files:
            pattern = r"(?:q)?(\d+)" if src.is_dir() else r"(?:q)?(\d+)(?:and)?"
            match = re.fullmatch(pattern, path.stem, re.IGNORECASE)
            if not match:
                if src.is_dir():
                    continue
                raise ValueError(f"O nome {path.name!r} deve identificar a query, por exemplo 0005.json.")
            qid = int(match[1])
            if selected and qid not in selected:
                continue
            if qid in seen:
                raise ValueError(f"Q{qid} repetida em {name}.")
            seen.add(qid)
            matched += 1
            query = f"q{qid:02d}"
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
            queries.setdefault(query, payload["query"])
            docs = fetch(endpoint, payload, top)
            print(f"{query} · {name}: {len(docs)} resultados", flush=True)
            ids = set()
            for rank, doc in enumerate(docs, 1):
                doc_id = str(doc["id"])
                if doc_id in ids:
                    raise ValueError(f"Documento {doc_id} aparece duas vezes em {query}/{name}.")
                ids.add(doc_id)
                key = f"{query}/{doc_id}"
                if key not in articles:
                    body = doc.get("text") or ""
                    if isinstance(body, list):
                        body = "\n\n".join(map(str, body))
                    articles[key] = {"query": query, "doc_id": doc_id,
                                     "title": doc["title"], "body": body}
                    if not body:
                        print(f"Aviso: {key} não tem corpo devolvido no campo text.", flush=True)
                rankings.append({"key": key, "config": name, "rank": rank})
        if not matched or (selected and seen != selected):
            raise ValueError(f"Não encontrei todos os JSON das queries pedidas em {src}.")
    if not rankings:
        raise ValueError("Nenhuma configuração devolveu resultados.")
    order = sorted(articles, key=lambda k: (int(articles[k]["query"][1:]), articles[k]["title"].casefold(), k))
    return {"queries": queries, "articles": articles, "rankings": rankings,
            "order": order, "labels": {}}


def csv_bytes(session):
    file = io.StringIO(newline="")
    writer = csv.writer(file)
    writer.writerow(["query", "config", "title", "relevance", "rank", "doc_id"])
    for item in sorted(session["rankings"], key=lambda r: (int(r["key"].split("/")[0][1:]),
                                                        r["config"], r["rank"])):
        key = item["key"]
        doc = session["articles"][key]
        writer.writerow([doc["query"], item["config"], doc["title"],
                         session["labels"].get(key, ""), item["rank"], doc["doc_id"]])
    return file.getvalue().encode("utf-8-sig")


STYLE = """
*{box-sizing:border-box} body{font:16px system-ui,sans-serif;color:#172a36;
background:#f3f6f8;margin:0 auto;max-width:980px;padding:24px}
header,main{background:white;padding:20px 24px;border:1px solid #d8e2e8;
border-radius:12px;margin-bottom:14px} h1{font-size:22px;margin:0 0 8px}
h2{font-size:28px;margin:0 0 8px} p{margin:6px 0 12px} .status{color:#415a69}
.body{white-space:pre-wrap;overflow-wrap:anywhere;font:17px/1.55 system-ui;
max-height:55vh;overflow:auto;border-top:1px solid #e1e8ec;padding-top:14px;
margin:14px 0 0} .bar{display:flex;flex-wrap:wrap;align-items:center;gap:8px}
a,button{display:inline-block;color:#113d58;border:1px solid #bbced8;
border-radius:7px;padding:7px 11px;text-decoration:none;background:white;font:inherit}
button{cursor:pointer}button.selected{background:#174d69;color:white;border-color:#174d69}
button:hover,a:hover{outline:2px solid #6d9db4;outline-offset:1px}
a[aria-disabled=true]{color:#60717b;border-color:#e1e8ec}
"""


def handler_for(session, state):
    token = secrets.token_urlsafe(24)
    order = session["order"]
    labels = session["labels"]
    esc = html.escape

    def first_unjudged(start):
        return next((i for i in (*range(start, len(order)), *range(0, start))
                     if order[i] not in labels), None)

    def page(i):
        key = order[i]
        doc = session["articles"][key]
        question = session["queries"][doc["query"]]
        current = labels.get(key)
        next_empty = first_unjudged(i)
        status = ("Sem juízo" if current is None else
                  ("Relevante (1)" if current == 1 else "Não relevante (0)"))
        prev = f'<a href="/?i={i-1}">Anterior</a>' if i else '<a aria-disabled="true">Anterior</a>'
        nxt = (f'<a href="/?i={i+1}">Seguinte</a>' if i+1 < len(order) else
               '<a aria-disabled="true">Seguinte</a>')
        jump = (f'<a href="/?i={next_empty}">Por classificar</a>' if next_empty is not None else "")
        return f"""<!doctype html><html lang="pt"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Avaliação Solr</title><style>{STYLE}</style>
<header><h1>Avaliação Solr</h1><p class="status">{len(labels)} / {len(order)} pares
avaliados · artigo {i+1} de {len(order)} · {status}</p>
<p><strong>{esc(doc['query'].upper())}</strong> — {esc(question)}</p>
<form class="bar" action="/judge" method="post">
<input type="hidden" name="i" value="{i}"><input type="hidden" name="token" value="{token}">
<button id="label0" name="label" value="0" class="{'selected' if current == 0 else ''}">0 · Não relevante</button>
<button id="label1" name="label" value="1" class="{'selected' if current == 1 else ''}">1 · Relevante</button>
{prev}{nxt}{jump}<a href="/export">Descarregar CSV</a></form></header>
<main><h2>{esc(doc['title'])}</h2>
<article class="body" tabindex="0">{esc(doc['body'] or 'O Solr não devolveu o corpo deste artigo.')}</article></main>
<script>document.addEventListener('keydown',e=>{{
  if (e.repeat || e.ctrlKey || e.altKey || e.metaKey || !['0','1'].includes(e.key)) return;
  document.getElementById('label'+e.key).click();
}});</script></html>""".encode("utf-8")

    class JudgeHandler(BaseHTTPRequestHandler):
        def send(self, body, content_type, filename=None):
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            url = urlsplit(self.path)
            if url.path == "/export":
                return self.send(csv_bytes(session), "text/csv; charset=utf-8", "juizos_solr.csv")
            if url.path != "/":
                return self.send_error(404)
            try:
                i = int(parse_qs(url.query).get("i", [first_unjudged(0) or 0])[0])
                if not 0 <= i < len(order):
                    raise ValueError
            except ValueError:
                return self.send_error(400, "Posição inválida")
            self.send(page(i), "text/html; charset=utf-8")

        def do_POST(self):
            if self.path != "/judge":
                return self.send_error(404)
            try:
                length = int(self.headers.get("Content-Length", 0))
                if not 0 < length <= 4096:
                    raise ValueError
                form = parse_qs(self.rfile.read(length).decode("utf-8"))
                i = int(form["i"][0])
                value = form["label"][0]
                if form["token"][0] != token or value not in {"0", "1"} or not 0 <= i < len(order):
                    raise ValueError
            except (KeyError, ValueError):
                return self.send_error(400, "Juízo inválido")
            key = order[i]
            previous = labels.get(key)
            labels[key] = int(value)
            try:
                save(state, session)
            except OSError as err:
                if previous is None:
                    labels.pop(key)
                else:
                    labels[key] = previous
                return self.send_error(500, explain=str(err))
            next_item = first_unjudged(i+1)
            self.send_response(303)
            self.send_header("Location", f"/?i={i if next_item is None else next_item}")
            self.end_headers()

        def log_message(self, *_args):
            pass

    return JudgeHandler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="append", metavar="NOME=CAMINHO",
                        help="Pasta de configurações ou ficheiro 0005.json. Pode repetir-se.")
    parser.add_argument("--query", type=int, action="append", help="Avaliar só esta query. Pode repetir-se.")
    parser.add_argument("--solr", default=None, help=f"URL do endpoint de pesquisa. Por omissão: {SOLR}")
    parser.add_argument("--top", type=int, default=None, help="Máximo de resultados por configuração. Por omissão: 20.")
    parser.add_argument("--state", type=Path, default=Path("sessao_juizos.json"),
                        help="Ficheiro de sessão para guardar e retomar os juízos.")
    parser.add_argument("--no-browser", action="store_true", help="Mostra o URL sem abrir o browser.")
    args = parser.parse_args()
    state = args.state.expanduser()
    try:
        if state.exists():
            if args.run or args.query or args.solr or args.top is not None:
                parser.error("A sessão já existe. Retoma só com --state, ou escolhe outro --state para uma nova avaliação.")
            session = json.loads(state.read_text(encoding="utf-8"))
        else:
            if not args.run:
                parser.error("Indica pelo menos um --run NOME=CAMINHO para iniciar a sessão.")
            if args.top is not None and args.top < 1:
                parser.error("--top tem de ser pelo menos 1.")
            session = make_session(args.run, args.solr or SOLR, set(args.query or []), args.top or 20)
            state.parent.mkdir(parents=True, exist_ok=True)
            save(state, session)
    except (OSError, ValueError, KeyError) as err:
        parser.exit(1, f"Não foi possível iniciar a avaliação: {err}\n")
    with HTTPServer(("127.0.0.1", 0), handler_for(session, state)) as server:
        url = f"http://127.0.0.1:{server.server_port}/"
        print(f"Interface: {url}\nSessão: {state.resolve()}\nCtrl+C para sair.", flush=True)
        if not args.no_browser:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nSessão guardada.")


if __name__ == "__main__":
    main()
