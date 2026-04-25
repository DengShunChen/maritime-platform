/**
 * Data Preloader Utility
 * 
 * Prefetches data for upcoming time points to improve perceived performance.
 * Uses requestIdleCallback for non-blocking prefetching.
 */

interface IdleRequestOptions {
  timeout?: number;
}

interface WindowWithIdleCallback {
  requestIdleCallback: (callback: () => void, options?: IdleRequestOptions) => number;
}

class DataPreloader {
  private preloadQueue: Set<string> = new Set();
  private preloadedUrls: Set<string> = new Set();
  private isPreloading: boolean = false;
  private maxCacheSize: number = 20;

  /**
   * Prefetch a URL during browser idle time
   */
  prefetch(url: string, priority: 'high' | 'low' = 'low'): void {
    if (this.preloadedUrls.has(url) || this.preloadQueue.has(url)) {
      return;
    }

    this.preloadQueue.add(url);

    if (priority === 'high') {
      this.processQueue();
    } else {
      this.scheduleProcessing();
    }
  }

  /**
   * Prefetch stats for a specific time index.
   * Tiles are served by TiTiler directly — no need to warm a separate tile cache.
   */
  prefetchTimePoint(
    timeIndex: number,
    variable: string
  ): void {
    // Only prefetch stats; TiTiler handles tile caching internally
    const statsUrl = `/api/variable_stats?time=${timeIndex}&variable=${variable}`;
    this.prefetch(statsUrl, 'low');
  }

  /**
   * Prefetch wind texture for a specific time index
   */
  prefetchWindData(timeIndex: number): void {
    const windTextureUrl = `/api/wind_texture?time=${timeIndex}`;
    this.prefetch(windTextureUrl, 'high');
  }

  /**
   * Schedule queue processing during idle time
   */
  private scheduleProcessing(): void {
    if (this.isPreloading) return;

    if ('requestIdleCallback' in window) {
      (window as unknown as WindowWithIdleCallback).requestIdleCallback(
        () => this.processQueue(),
        { timeout: 2000 }
      );
    } else {
      setTimeout(() => this.processQueue(), 100);
    }
  }

  /**
   * Process the preload queue
   */
  private processQueue(): void {
    if (this.preloadQueue.size === 0) {
      this.isPreloading = false;
      return;
    }

    this.isPreloading = true;
    const url = this.preloadQueue.values().next().value;
    
    if (url) {
      this.preloadQueue.delete(url);
      
      fetch(url, { priority: 'low' } as RequestInit)
        .then(() => {
          this.preloadedUrls.add(url);
          this.trimCache();
        })
        .catch(() => {
          // Silently fail - prefetching is optional
        })
        .finally(() => {
          this.isPreloading = false;
          if (this.preloadQueue.size > 0) {
            this.scheduleProcessing();
          }
        });
    }
  }

  /**
   * Trim cache if it exceeds max size
   */
  private trimCache(): void {
    if (this.preloadedUrls.size > this.maxCacheSize) {
      const iterator = this.preloadedUrls.values();
      const firstUrl = iterator.next().value;
      if (firstUrl) {
        this.preloadedUrls.delete(firstUrl);
      }
    }
  }

  /**
   * Check if a URL has been preloaded
   */
  isPreloaded(url: string): boolean {
    return this.preloadedUrls.has(url);
  }

  /**
   * Clear all preloaded data
   */
  clear(): void {
    this.preloadQueue.clear();
    this.preloadedUrls.clear();
    this.isPreloading = false;
  }
}

// Export singleton instance
export const dataPreloader = new DataPreloader();

// Hook for React components
export function usePrefetch(
  currentTimeIndex: number,
  totalTimePoints: number,
  selectedVariable: string,
  enabled: boolean = true
): void {
  if (!enabled || totalTimePoints === 0) return;

  // Prefetch next 2 time points
  const nextIndices = [
    currentTimeIndex + 1,
    currentTimeIndex + 2
  ].filter(i => i < totalTimePoints);

  nextIndices.forEach(idx => {
    if (selectedVariable === 'WIND') {
      dataPreloader.prefetchWindData(idx);
      dataPreloader.prefetchTimePoint(idx, 'WSPD');
    } else {
      dataPreloader.prefetchTimePoint(idx, selectedVariable);
    }
  });
}
