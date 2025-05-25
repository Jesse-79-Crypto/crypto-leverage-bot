timeout = 240          # 4 minutes for blockchain operations

keepalive = 120        # Keep connections alive

max_requests = 1000    # Restart workers periodically

preload_app = True     # Improve performance

workers = 1            # Single worker for consistent state

worker_class = 'sync'  # Synchronous worker
