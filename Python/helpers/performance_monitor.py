"""
Performance monitoring and metrics collection for Unreal MCP Server.

Provides Prometheus metrics, OpenTelemetry tracing, and performance analytics.
"""

import logging
import time
import functools
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from collections import defaultdict
import threading

logger = logging.getLogger(__name__)

# Try to import Prometheus, fall back to basic metrics
try:
    from prometheus_client import Counter, Histogram, Gauge, Info, Summary
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    logger.warning("Prometheus client not available, using basic metrics")


@dataclass
class MetricData:
    """Container for metric data."""
    count: int = 0
    total: float = 0.0
    min: float = float('inf')
    max: float = 0.0
    errors: int = 0
    
    def update(self, value: float, is_error: bool = False):
        """Update metric with new value."""
        self.count += 1
        self.total += value
        self.min = min(self.min, value)
        self.max = max(self.max, value)
        if is_error:
            self.errors += 1
    
    @property
    def average(self) -> float:
        """Calculate average."""
        return self.total / self.count if self.count > 0 else 0.0
    
    @property
    def error_rate(self) -> float:
        """Calculate error rate percentage."""
        return (self.errors / self.count * 100) if self.count > 0 else 0.0


class MetricsCollector:
    """
    Metrics collector with Prometheus support.
    
    Features:
    - Command execution metrics
    - Latency tracking
    - Error rates
    - Resource usage
    - Custom metrics
    """
    
    def __init__(self, use_prometheus: bool = True):
        self.use_prometheus = use_prometheus and PROMETHEUS_AVAILABLE
        
        # Basic metrics storage
        self.metrics: Dict[str, MetricData] = defaultdict(MetricData)
        self._lock = threading.Lock()
        
        # Prometheus metrics
        if self.use_prometheus:
            self._init_prometheus_metrics()
    
    def _init_prometheus_metrics(self):
        """Initialize Prometheus metrics."""
        # Counters
        self.prom_commands_total = Counter(
            'unreal_mcp_commands_total',
            'Total number of commands executed',
            ['command', 'status']
        )
        
        self.prom_errors_total = Counter(
            'unreal_mcp_errors_total',
            'Total number of errors',
            ['command', 'error_type']
        )
        
        # Histograms
        self.prom_command_duration = Histogram(
            'unreal_mcp_command_duration_seconds',
            'Command execution duration',
            ['command'],
            buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
        )
        
        # Gauges
        self.prom_active_connections = Gauge(
            'unreal_mcp_active_connections',
            'Number of active connections'
        )
        
        self.prom_cache_size = Gauge(
            'unreal_mcp_cache_size',
            'Current cache size'
        )
        
        # Summary
        self.prom_request_size = Summary(
            'unreal_mcp_request_size_bytes',
            'Request payload size'
        )
        
        # Info
        self.prom_server_info = Info(
            'unreal_mcp_server',
            'Server information'
        )
        
        logger.info("Prometheus metrics initialized")
    
    def record_command(
        self,
        command: str,
        duration: float,
        success: bool = True,
        error_type: Optional[str] = None
    ):
        """Record command execution."""
        with self._lock:
            # Basic metrics
            metric_key = f"command:{command}"
            self.metrics[metric_key].update(duration, is_error=not success)
            
            # Prometheus metrics
            if self.use_prometheus:
                status = "success" if success else "error"
                self.prom_commands_total.labels(
                    command=command,
                    status=status
                ).inc()
                
                self.prom_command_duration.labels(
                    command=command
                ).observe(duration)
                
                if error_type:
                    self.prom_errors_total.labels(
                        command=command,
                        error_type=error_type
                    ).inc()
    
    def set_active_connections(self, count: int):
        """Set number of active connections."""
        if self.use_prometheus:
            self.prom_active_connections.set(count)
    
    def set_cache_size(self, size: int):
        """Set cache size."""
        if self.use_prometheus:
            self.prom_cache_size.set(size)
    
    def record_request_size(self, size: int):
        """Record request payload size."""
        if self.use_prometheus:
            self.prom_request_size.observe(size)
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get all metrics."""
        with self._lock:
            return {
                metric_name: {
                    "count": data.count,
                    "average": data.average,
                    "min": data.min if data.min != float('inf') else 0,
                    "max": data.max,
                    "total": data.total,
                    "errors": data.errors,
                    "error_rate": data.error_rate
                }
                for metric_name, data in self.metrics.items()
            }
    
    def get_summary(self) -> Dict[str, Any]:
        """Get metrics summary."""
        metrics = self.get_metrics()
        
        total_commands = sum(m["count"] for m in metrics.values())
        total_errors = sum(m["errors"] for m in metrics.values())
        
        return {
            "total_commands": total_commands,
            "total_errors": total_errors,
            "overall_error_rate": (
                total_errors / total_commands * 100
                if total_commands > 0 else 0
            ),
            "commands": metrics
        }


class PerformanceMonitor:
    """
    Performance monitoring with timing and profiling.
    
    Features:
    - Function timing
    - Context manager timing
    - Performance warnings
    - Slow query detection
    """
    
    def __init__(
        self,
        collector: Optional[MetricsCollector] = None,
        slow_threshold: float = 1.0
    ):
        self.collector = collector or MetricsCollector()
        self.slow_threshold = slow_threshold
    
    def time_function(
        self,
        func: Callable,
        *args,
        **kwargs
    ) -> tuple[Any, float]:
        """
        Time function execution.
        
        Returns:
            Tuple of (result, duration)
        """
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            duration = time.time() - start_time
            
            # Record metrics
            self.collector.record_command(
                func.__name__,
                duration,
                success=True
            )
            
            # Warn if slow
            if duration > self.slow_threshold:
                logger.warning(
                    f"Slow function: {func.__name__} took {duration:.2f}s"
                )
            
            return result, duration
            
        except Exception as e:
            duration = time.time() - start_time
            
            # Record error
            self.collector.record_command(
                func.__name__,
                duration,
                success=False,
                error_type=type(e).__name__
            )
            
            raise
    
    def __call__(self, func: Callable) -> Callable:
        """Decorator for timing functions."""
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            result, _ = self.time_function(func, *args, **kwargs)
            return result
        return wrapper
    
    def __enter__(self):
        """Context manager entry."""
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        duration = time.time() - self.start_time
        
        if duration > self.slow_threshold:
            logger.warning(f"Slow operation took {duration:.2f}s")


# Global metrics collector
_metrics_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    """Get global metrics collector."""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector


def monitor_performance(command_name: Optional[str] = None):
    """
    Decorator for monitoring function performance.
    
    Example:
        @monitor_performance("create_blueprint")
        def create_blueprint(name: str):
            # Function implementation
            pass
    """
    def decorator(func):
        nonlocal command_name
        if command_name is None:
            command_name = func.__name__
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            collector = get_metrics_collector()
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                
                collector.record_command(
                    command_name,
                    duration,
                    success=True
                )
                
                return result
                
            except Exception as e:
                duration = time.time() - start_time
                
                collector.record_command(
                    command_name,
                    duration,
                    success=False,
                    error_type=type(e).__name__
                )
                
                raise
        
        return wrapper
    return decorator
