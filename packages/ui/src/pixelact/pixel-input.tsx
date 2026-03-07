import * as React from 'react';
import { cn } from '../utils';

export interface PixelInputProps
  extends React.InputHTMLAttributes<HTMLInputElement> {}

const PixelInput = React.forwardRef<HTMLInputElement, PixelInputProps>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn('pxa-input w-full', className)}
        ref={ref}
        {...props}
      />
    );
  },
);
PixelInput.displayName = 'PixelInput';

export { PixelInput };
