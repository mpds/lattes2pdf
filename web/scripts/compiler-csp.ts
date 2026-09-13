import type { Plugin } from 'vite';

/** typst.ts 0.7.0's dummy filesystem callbacks use Function for fixed strings.
 * Replace only those exact functions, without enabling JavaScript evaluation.
 * Actual filesystem/package access is supplied by our in-memory adapter.
 */
export function compilerCsp(): Plugin {
  return {
    name: 'compiler-csp',
    transform(code, id) {
      if (!id.endsWith('typst_ts_web_compiler.mjs')) return;
      const noArgs = 'new Function(getStringFromWasm0(arg0, arg1))';
      const withArgs =
        'new Function(getStringFromWasm0(arg0, arg1), getStringFromWasm0(arg2, arg3))';
      if (
        code.split(noArgs).length !== 2 ||
        code.split(withArgs).length !== 2
      ) {
        throw new Error('Compiler changed: review its CSP adapter.');
      }
      return code
        .replace(
          noArgs,
          `(() => {
        const body = getStringFromWasm0(arg0, arg1);
        if (body === 'return 0') return () => 0;
        if (body === 'return true') return () => true;
        if (body === 'return this') return () => globalThis;
        if (body === "throw new Error('Dummy AccessModel, please initialize compiler with withAccessModel()')" ||
            body === "throw new Error('Dummy Registry, please initialize compiler with withPackageRegistry()')") {
          return () => { throw new Error('Compiler resource adapter is missing.'); };
        }
        throw new Error('Unsupported compiler callback.');
      })()`,
        )
        .replace(
          withArgs,
          `(() => {
        if (getStringFromWasm0(arg0, arg1) === 'path' && getStringFromWasm0(arg2, arg3) === 'return path') return path => path;
        throw new Error('Unsupported compiler callback arguments.');
      })()`,
        );
    },
  };
}
