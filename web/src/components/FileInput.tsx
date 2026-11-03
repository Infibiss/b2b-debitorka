import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
  type InputHTMLAttributes,
} from 'react';
import { Upload } from 'lucide-react';
import './file-input.css';

type FileInputProps = Omit<
  InputHTMLAttributes<HTMLInputElement>,
  'type' | 'value' | 'defaultValue'
>;

/** Keeps the native picker and FormData contract while giving every upload a Russian label. */
export const FileInput = forwardRef<HTMLInputElement, FileInputProps>(function FileInput(
  { onChange, className = '', multiple, ...props },
  forwardedRef
) {
  const input = useRef<HTMLInputElement>(null);
  const [names, setNames] = useState('');
  useImperativeHandle(forwardedRef, () => input.current!, []);
  useEffect(() => {
    const form = input.current?.form;
    const reset = (event: Event) => {
      queueMicrotask(() => {
        if (!event.defaultPrevented) setNames('');
      });
    };
    form?.addEventListener('reset', reset);
    return () => form?.removeEventListener('reset', reset);
  }, []);
  return (
    <span className="file-picker">
      <span className="file-picker-button" aria-hidden="true">
        <Upload size={16} />
        {multiple ? 'Выбрать файлы' : 'Выбрать файл'}
      </span>
      <span className="file-picker-name" aria-hidden="true" title={names}>
        {names || 'Файл не выбран'}
      </span>
      <input
        {...props}
        ref={input}
        className={`file-picker-input ${className}`}
        type="file"
        multiple={multiple}
        onChange={(event) => {
          setNames(
            Array.from(event.currentTarget.files || [])
              .map((file) => file.name)
              .join(', ')
          );
          onChange?.(event);
        }}
      />
    </span>
  );
});
