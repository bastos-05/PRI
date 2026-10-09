IMAGE = crawler
CONTAINER = crawler-container

.PHONY: build run start stop clean rebuild

build:
	docker build -t $(IMAGE) .

run:
	docker run --name $(CONTAINER) -v $(CURDIR)/src:/app/src $(IMAGE)

start:
	docker start -a $(CONTAINER)

stop:
	docker stop $(CONTAINER)

clean:
	docker rm -f $(CONTAINER)

rebuild: build
	docker rm -f $(CONTAINER) 2>/dev/null || true
	docker run --name $(CONTAINER) -v $(CURDIR)/src:/app/src $(IMAGE)
