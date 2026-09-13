# Ring-0 request: actual execution boundary

The native host application is a normal user process. It requests CUDA work
through the installed NVIDIA software stack. The operating system and existing
driver enforce the device interface. A CUDA kernel is a GPU entry-point function;
that term does not grant CPU ring-0 privileges.

No additional privileged component is necessary for the texture-object interface
used by this package. Driver-level code would not convert a read-only texture
cache into instruction storage or provide a guarantee of cache pinning.

For a future legitimate OS integration, keep a small separately reviewed and
platform-approved driver for device-specific responsibilities, and leave the
model, programmable interpreter and journaling in user space. Windows has
kernel-driver signing requirements [N8]; user and kernel execution have different
failure/isolation consequences [N7]. That integration would be a separate
platform-specific deliverable, not a switch in this CUDA package.

There is no rootkit, arbitrary kernel-memory interface, hidden process, DMA
bypass, injected game component, unsigned-driver loading routine, driver-signing
disablement or covert persistence. The Mirage viewer is ordinary offline
presentation. Author metadata is not a privilege-bearing capability.

References N7–N8 are in SOURCES.md. No driver installation, device access or
privilege change was performed on the user's machine during this delivery.
