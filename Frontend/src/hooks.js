import { useCallback, useEffect, useRef, useState } from "react";

// A value that resets itself after `ms` (e.g. "Copied!" feedback). The timer is cleared
// when the component unmounts, so it never fires into a component that is gone.
export function useTransient(ms = 2000) {
  const [value, setValue] = useState(null);
  const timer = useRef(null);

  useEffect(() => () => clearTimeout(timer.current), []);

  const show = useCallback(
    (next = true) => {
      clearTimeout(timer.current);
      setValue(next);
      timer.current = setTimeout(() => setValue(null), ms);
    },
    [ms],
  );
  return [value, show];
}
