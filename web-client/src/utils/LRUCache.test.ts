import { describe, expect, it } from 'vitest';
import { LRUCache } from './LRUCache';

describe('LRUCache', () => {
  it('evicts oldest when over capacity', () => {
    const cache = new LRUCache<string, number>(2);
    cache.set('a', 1);
    cache.set('b', 2);
    cache.set('c', 3);
    expect(cache.has('a')).toBe(false);
    expect(cache.get('b')).toBe(2);
    expect(cache.get('c')).toBe(3);
  });

  it('refreshes order on get', () => {
    const cache = new LRUCache<string, number>(2);
    cache.set('a', 1);
    cache.set('b', 2);
    cache.get('a');
    cache.set('c', 3);
    expect(cache.has('b')).toBe(false);
    expect(cache.get('a')).toBe(1);
  });

  it('clears all entries', () => {
    const cache = new LRUCache<string, number>(10);
    cache.set('x', 1);
    cache.clear();
    expect(cache.size).toBe(0);
  });
});
