import { createFileRoute } from '@tanstack/react-router';

import { DesignGallery } from '../../ui/gallery/DesignGallery';

// Design gallery for review and screenshots. Deliberately absent from NAV_SECTIONS.
export const Route = createFileRoute('/dev/design')({
  component: DesignGallery,
});
