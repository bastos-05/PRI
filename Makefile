IMAGE = crawler
CONTAINER = crawler-container

.PHONY: build run start stop clean rebuild list

build:
	docker build -t $(IMAGE) .

run:
	docker run --name $(CONTAINER) -v $(CURDIR)/src:/app/src -v $(CURDIR)/data:/app/data -v $(CURDIR)/models:/app/models $(IMAGE)

start:
	docker start -a $(CONTAINER)

stop:
	docker stop $(CONTAINER)

clean:
	docker rm -f $(CONTAINER)

rebuild: build
	docker rm -f $(CONTAINER) 2>/dev/null || true
	docker run --name $(CONTAINER) -v $(CURDIR)/src:/app/src -v $(CURDIR)/data:/app/data -v $(CURDIR)/models:/app/models $(IMAGE)

list:
	@docker exec crawler-container python -c "\
	import sqlite3; \
	conn = sqlite3.connect('/app/data/crawler.db'); \
	rows = conn.execute('SELECT depth, COUNT(*), SUM(processed) FROM categories GROUP BY depth ORDER BY depth').fetchall(); \
	print('Depth | Total | Processed | Pending'); \
	[print(f'{d:5} | {total:5} | {done:9} | {total-done:7}') for d, total, done in rows]; \
	conn.close()"
