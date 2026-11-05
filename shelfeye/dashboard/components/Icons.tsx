// Small stroke icons (24×24 grid), drawn in the current text colour.
import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function Icon({ size = 18, children, ...props }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      {children}
    </svg>
  );
}

export const OverviewIcon = (p: IconProps) => (
  <Icon {...p}><rect x="3" y="3" width="7" height="9" rx="1.5" /><rect x="14" y="3" width="7" height="5" rx="1.5" /><rect x="14" y="12" width="7" height="9" rx="1.5" /><rect x="3" y="16" width="7" height="5" rx="1.5" /></Icon>
);
export const BoxIcon = (p: IconProps) => (
  <Icon {...p}><path d="M21 8 12 3 3 8v8l9 5 9-5V8z" /><path d="m3 8 9 5 9-5" /><path d="M12 13v8" /></Icon>
);
export const ActivityIcon = (p: IconProps) => (
  <Icon {...p}><path d="M3 12h4l3-8 4 16 3-8h4" /></Icon>
);
export const CameraIcon = (p: IconProps) => (
  <Icon {...p}><path d="M4 8h3l2-3h6l2 3h3a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1z" /><circle cx="12" cy="13.5" r="3.5" /></Icon>
);
export const AlertIcon = (p: IconProps) => (
  <Icon {...p}><path d="M10.3 4.2 2.6 18a2 2 0 0 0 1.7 3h15.4a2 2 0 0 0 1.7-3L13.7 4.2a2 2 0 0 0-3.4 0z" /><path d="M12 9.5v4" /><path d="M12 17h.01" /></Icon>
);
export const ArrowDownIcon = (p: IconProps) => (
  <Icon {...p}><path d="M12 5v14" /><path d="m6 13 6 6 6-6" /></Icon>
);
export const ArrowUpIcon = (p: IconProps) => (
  <Icon {...p}><path d="M12 19V5" /><path d="m6 11 6-6 6 6" /></Icon>
);
export const VideoIcon = (p: IconProps) => (
  <Icon {...p}><rect x="2.5" y="6" width="13" height="12" rx="2" /><path d="m15.5 10.5 6-3.5v10l-6-3.5" /></Icon>
);
export const SearchIcon = (p: IconProps) => (
  <Icon {...p}><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></Icon>
);
export const LogOutIcon = (p: IconProps) => (
  <Icon {...p}><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><path d="m16 17 5-5-5-5" /><path d="M21 12H9" /></Icon>
);
export const EyeIcon = (p: IconProps) => (
  <Icon {...p}><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7-10-7-10-7z" /><circle cx="12" cy="12" r="3" /></Icon>
);
export const EyeOffIcon = (p: IconProps) => (
  <Icon {...p}><path d="M9.9 5.2A10.8 10.8 0 0 1 12 5c6.4 0 10 7 10 7a17.6 17.6 0 0 1-3.2 4.2" /><path d="M6.6 6.6C3.8 8.4 2 12 2 12s3.6 7 10 7a9.7 9.7 0 0 0 5.4-1.6" /><path d="M14.1 14.1a3 3 0 0 1-4.2-4.2" /><path d="m2 2 20 20" /></Icon>
);
export const CheckIcon = (p: IconProps) => (
  <Icon {...p}><path d="m5 12.5 4.5 4.5L19 7.5" /></Icon>
);
export const ChevronRightIcon = (p: IconProps) => (
  <Icon {...p}><path d="m9 6 6 6-6 6" /></Icon>
);
export const ClockIcon = (p: IconProps) => (
  <Icon {...p}><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></Icon>
);

/** The ShelfEye mark: a white eye on an orange tile. */
export function Logo({ size = 34 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 34 34" aria-hidden="true">
      <rect width="34" height="34" rx="9" fill="#f97316" />
      <path d="M5.5 17s4.5-8 11.5-8 11.5 8 11.5 8-4.5 8-11.5 8S5.5 17 5.5 17z" fill="#fff" />
      <circle cx="17" cy="17" r="3.8" fill="#f97316" />
      <circle cx="18.3" cy="15.7" r="1.1" fill="#fff" />
    </svg>
  );
}
export const SettingsIcon = (p: IconProps) => (
  <Icon {...p}><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" /></Icon>
);
export const PlusIcon = (p: IconProps) => (
  <Icon {...p}><path d="M12 5v14" /><path d="M5 12h14" /></Icon>
);
export const TrashIcon = (p: IconProps) => (
  <Icon {...p}><path d="M4 7h16" /><path d="M10 11v6" /><path d="M14 11v6" /><path d="M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12" /><path d="M9 7V4h6v3" /></Icon>
);
export const SidebarCollapseIcon = (p: IconProps) => (
  <Icon {...p}><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M9 4v16" /><path d="m16 10-2 2 2 2" /></Icon>
);
export const SidebarExpandIcon = (p: IconProps) => (
  <Icon {...p}><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M9 4v16" /><path d="m14 10 2 2-2 2" /></Icon>
);
