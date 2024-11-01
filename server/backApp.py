from server.ServerWorker import ServerWorker
from server.RemoteWorker import RemoteWorker
from server.debug_print import debug_print
from multiprocessing import Pool 
import time

def worker_fn(worker_id):
    debug_print(f"enter {worker_id}")
    worker = ServerWorker(worker_id)

    while worker.should_run():
        time.sleep(1)

def remote_worker_fn(worker_id):
    debug_print(f"enter {worker_id}")

    worker = RemoteWorker()
    while worker.should_run():
        time.sleep(1)


def main():
    threads = 4
    pool = Pool(processes=threads)
    pool.map_async(worker_fn, range(threads))

    remote_worker_fn(threads)

    pool.close()
    pool.join()

if __name__ == "__main__":
    main()
