from embeddings_filter import start_filtering
from download_model import download_model


def main():
    download_model()
    start_filtering()

if __name__ == '__main__':
    main()