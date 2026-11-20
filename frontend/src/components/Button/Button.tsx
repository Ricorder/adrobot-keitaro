import styles from './Button.module.css';
import type { ButtonProps, ButtonVariant } from './Button.types';

const VARIANT_CLASS: Record<ButtonVariant, string> = {
  primary: styles.primary,
  ghost: styles.ghost,
  danger: styles.danger
};

export function Button({ variant = 'ghost', className, type = 'button', ...rest }: ButtonProps) {
  const classes = [styles.base, VARIANT_CLASS[variant]];
  if (className !== undefined) classes.push(className);
  return <button type={type} className={classes.join(' ')} {...rest} />;
}
