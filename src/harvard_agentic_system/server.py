"""vLLM OpenAI-compatible server manager for accurate metrics collection."""

import subprocess
import time
import requests
import logging

logger = logging.getLogger(__name__)


class VLLMServer:
    """Manages a vLLM OpenAI-compatible server process."""

    def __init__(
        self,
        model: str,
        host: str = "localhost",
        port: int = 8000,
        gpu_memory_utilization: float = 0.9,
    ):
        """
        Initialize the vLLM server manager.

        Args:
            model: Model name to serve (e.g., "mistralai/Mistral-7B-Instruct-v0.3")
            host: Host to bind the server to
            port: Port to bind the server to
            gpu_memory_utilization: Fraction of GPU memory to use (0.0-1.0)
        """
        self.model = model
        self.host = host
        self.port = port
        self.gpu_memory_utilization = gpu_memory_utilization
        self.process: subprocess.Popen | None = None
        self.base_url = f"http://{host}:{port}"

    def start(self, timeout: int = 300) -> None:
        """
        Start the vLLM server.

        Args:
            timeout: Maximum time to wait for server to be ready (seconds)

        Raises:
            RuntimeError: If server fails to start
        """
        if self.process is not None:
            logger.warning("Server already running")
            return

        logger.info(f"Starting vLLM server for model: {self.model}")
        logger.info(f"Server will be available at: {self.base_url}")

        # Start vLLM server process
        # Use --disable-log-requests to reduce noise in logs
        cmd = [
            "vllm",
            "serve",
            self.model,
            "--host",
            self.host,
            "--port",
            str(self.port),
            "--gpu-memory-utilization",
            str(self.gpu_memory_utilization),
            "--disable-log-requests",
        ]

        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Wait for server to be ready
        logger.info("Waiting for server to be ready...")
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                response = requests.get(f"{self.base_url}/health", timeout=1)
                if response.status_code == 200:
                    logger.info("Server is ready!")
                    return
            except requests.exceptions.RequestException:
                pass

            # Check if process has died
            if self.process.poll() is not None:
                stderr = self.process.stderr.read() if self.process.stderr else ""
                raise RuntimeError(f"vLLM server process died: {stderr}")

            time.sleep(2)

        # Timeout
        self.stop()
        raise RuntimeError(f"Server failed to start within {timeout} seconds")

    def stop(self) -> None:
        """Stop the vLLM server."""
        if self.process is None:
            return

        logger.info("Stopping vLLM server...")
        self.process.terminate()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            logger.warning("Server did not stop gracefully, killing...")
            self.process.kill()
            self.process.wait()

        self.process = None
        logger.info("Server stopped")

    def is_running(self) -> bool:
        """Check if the server is running."""
        if self.process is None:
            return False

        if self.process.poll() is not None:
            return False

        try:
            response = requests.get(f"{self.base_url}/health", timeout=1)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()
