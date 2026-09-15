# Primary reference register

Inspected during R12 source review on 15 September 2026. These references
support the particular optical or detector claims indicated, not a complete
photonic implementation of the seed. The supplied source PDF is the primary
source for the WANTWOMBAN equations; its SHA and page count are in
SOURCE_BINDING.json. Derivations added by R12 are identified as such.

| PDF label | Primary source | Used claim and scope |
|---|---|---|
| P1 | [MIT rectangular-aperture optics demonstration](https://ocw.mit.edu/courses/res-6-006-video-demonstrations-in-lasers-and-optics-spring-2008/e06ca88aa4b673d48884b8705496a1b7_4YPxRTFxy2A.pdf) | Rectangular-aperture Fourier/diffraction dependence within the stated optical approximation |
| P2 | [Berge and Peseux, 2000](https://link.springer.com/article/10.1007/s101890070029) | Publisher abstract: liquid lens controlled through electrocapillarity; no calibration of proposed geometry |
| P3 | [Davies and Lewis, 1970](https://link.springer.com/article/10.1007/BF01647093) | Quantum instrument framework; R12 finite Kraus specialization and coarse-graining proof stated explicitly |
| P4 | [NIST single-photon detectors](https://www.nist.gov/pml/productsservices/quantum-networks-nist/technologies-quantum-networks/single-photon-detectors) | Transition-edge detection through resistance change under its cryogenic operating conditions |
| P5 | [Bhatt, Fuller and Léonard, 2026](https://www.nature.com/articles/s41467-026-74970-5) | Optical Boolean primitives/full adders with thresholded readout; eight-bit sequence uses re-entered DMD inputs, camera/computer readout and power-dependent errors |
| P6 | [Zhou and colleagues, 2026](https://www.nature.com/articles/s41467-026-75750-x) | Microring logic/two-bit arithmetic with electrical inputs, optical outputs, electrical OR and digital timing/threshold processing |

The passive scaled-pinion construction is derived in R12 from the supplied
matrix and elementary linear algebra. It is not presented as an experimentally
built device described by P5 or P6.
