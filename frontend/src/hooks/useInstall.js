import { useSyncExternalStore } from 'react';
import { getSnapshot, subscribe } from '../offline/install';

const SERVER_STATE = { canPrompt: false, installed: false, ios: false, inApp: false, secure: true };

export default function useInstall() {
    return useSyncExternalStore(subscribe, getSnapshot, () => SERVER_STATE);
}
