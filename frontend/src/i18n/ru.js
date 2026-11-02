// Rus tarjimalari: har bir bo'lim o'z faylida (./ru/<bo'lim>.js), shu yerda birlashtiriladi.
// Kalit -- o'zbekcha matn, qiymat -- ruscha tarjima.
const files = import.meta.glob('./ru/*.js', { eager: true });

const ru = {};
for (const mod of Object.values(files)) Object.assign(ru, mod.default);

export default ru;
