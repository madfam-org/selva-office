import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '../utils';

const pixelButtonVariants = cva(
  'pxa-btn disabled:pointer-events-none disabled:opacity-50',
  {
    variants: {
      variant: {
        default: 'bg-pixelact-primary text-pixelact-primary-fg',
        secondary: 'bg-pixelact-muted text-pixelact-muted-fg',
        destructive: 'bg-semantic-error text-white',
        success: 'bg-semantic-success text-white',
        ghost: 'bg-transparent border-transparent shadow-none hover:bg-pixelact-muted',
      },
      size: {
        default: 'px-3 py-1.5 text-retro-sm',
        sm: 'px-2 py-1 text-retro-xs',
        lg: 'px-4 py-2 text-retro-base',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  },
);

export interface PixelButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof pixelButtonVariants> {}

const PixelButton = React.forwardRef<HTMLButtonElement, PixelButtonProps>(
  ({ className, variant, size, ...props }, ref) => {
    return (
      <button
        className={cn(pixelButtonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    );
  },
);
PixelButton.displayName = 'PixelButton';

export { PixelButton, pixelButtonVariants };
