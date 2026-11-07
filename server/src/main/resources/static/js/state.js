// Independent owners cancel reads AND reject late responses even if transport ignores abort.
export class Latest {
  constructor() { this.generation = 0; }
  next() {
    this.controller?.abort(); this.controller = new AbortController();
    const generation = ++this.generation;
    return {signal:this.controller.signal, current:() => generation === this.generation};
  }
  cancel() { this.controller?.abort(); this.generation++; }
}
export class Drafts {
  constructor(changed = () => {}) { this.items = new Map(); this.changed = changed; this.pending = 0; this.unknown = new Set(); }
  get(key, create) { if (!this.items.has(key)) this.items.set(key, {value:create(), dirty:false}); return this.items.get(key); }
  touch(key) { this.items.get(key).dirty = true; this.changed(); }
  clean(key) { if (this.items.has(key)) this.items.get(key).dirty = false; this.changed(); }
  remove(key) { this.items.delete(key); this.changed(); }
  count() { return [...this.items.values()].filter(d => d.dirty).length; }
}
