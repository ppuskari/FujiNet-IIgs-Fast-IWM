# Architecture

## Phase 1: transport only

```text
FujiNet RAM pattern source
        |
        v
standard SmartPort / Fast-IWM
        |
        v
      SPBENCH
        |
        v
throughput + latency + integrity results
```

No Wi-Fi, TCP, transcoding, DOC audio, Finder background service, or CDA work is
allowed to contaminate the initial transport benchmark.

## Phase 2: deterministic PCM

```text
FujiNet RAM-backed deterministic PCM
        |
        v
Fast-IWM streaming primitive
        |
        v
IIgs 512 KiB audio ring
        |
        v
existing exact 16 KiB producer/refill path
        |
        v
Ensoniq DOC
```

The existing consumer/refill architecture remains frozen while the transport is
substituted.

## Phase 3: network offload

```text
Internet/provider
      |
      v
FujiNet ESP32 Wi-Fi/TCP buffer
      |
      v
Fast-IWM
      |
      v
IIgs resident FStream service
      |
      v
DOC
```

The IIgs should not run TCP/IP in this architecture.  It consumes already
buffered PCM from FujiNet.

## Phase 4: resident system service

The long-term architecture separates hard real-time DOC servicing from soft
real-time producer servicing.

```text
DOC IRQ (short, deterministic)
  - identify oscillator event
  - refill safe DOC half from system-memory ring
  - update counters / set low-water flag
  - return

FStreamService (deferred)
  - inspect ring state
  - request Fast-IWM burst when needed
  - append PCM to system-memory ring
  - return
```

Finder, Manager-aware applications, a radio UI, and CDAs become clients of the
resident service rather than owners of the stream.
