# RobotController Java server

This reactor is the new Java 8 implementation area. The legacy `src/` tree remains a reference implementation.

## Modules

* `robot-controller-core`: protocol, backend/audio contracts, canonical PCM, bounded WAV decoding, and mouth-envelope analysis.
* `robot-controller-backend-mock`: deterministic robot and audio fakes for Windows tests.
* `robot-controller-backend-vstone`: reserved boundary for public VSTONE Java API adapters; no runtime adapter is implemented in the first slice.
* `robot-controller-app`: reserved composition root; the production TCP server is not implemented in the first slice.

## Build and test

The canonical command is:

```powershell
mvn -f .\java_server\pom.xml test
```

The compiler source and target are Java 8. Tests use only the Mock module and do not access robot hardware or an audio device.

## Initial audio format boundary

The first decoder deliberately accepts only bounded RIFF/WAVE files containing uncompressed PCM (`formatTag = 1`), one or two channels, and signed 16-bit little-endian samples. It rejects unsupported formats, inconsistent frame alignment, truncated chunks, excessive payload size, and excessive decoded duration. Decoding is memory-only. This is an implementation boundary for the first slice, not the final production format policy.
