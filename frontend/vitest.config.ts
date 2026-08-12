import {defineConfig} from 'vitest/config';
export default defineConfig({test:{environment:'jsdom',setupFiles:'./src/tests/setup.ts',css:true,coverage:{provider:'v8',include:['src/pages/Study.tsx','src/pages/MockExam.tsx','src/pages/WrongNotes.tsx','src/components/ContentProtection.tsx','src/components/StudyExitGuard.tsx'],thresholds:{lines:95,statements:95}}}});
