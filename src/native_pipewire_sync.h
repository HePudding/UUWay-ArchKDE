/* Synchronous acquire/release of PipeWire explicit DRM syncobj timelines.
 * The consumer finishes its GPU read before signalling release. Dropped
 * buffers also wait for acquire before release, so producers never reuse a
 * buffer while their previous render is still pending. No pixel mapping. */
#ifdef UURB_PIPEWIRE_EXPLICIT_SYNC
#include <xf86drm.h>

static int uurb_sync_handle(int *device, int fd, uint32_t *handle)
{
    if (*device >= 0) return drmSyncobjFDToHandle(*device, fd, handle);
    drmDevicePtr devices[32];
    int count = drmGetDevices2(0, devices, 32), result = -1;
    if (count < 0) return -1;
    for (int i = 0; i < count; i++) {
        if (!(devices[i]->available_nodes & (1 << DRM_NODE_RENDER))) continue;
        int candidate = open(devices[i]->nodes[DRM_NODE_RENDER], O_RDWR | O_CLOEXEC);
        if (candidate < 0) continue;
        if (!drmSyncobjFDToHandle(candidate, fd, handle)) {
            *device = candidate; result = 0; break;
        }
        close(candidate);
    }
    drmFreeDevices(devices, count);
    return result;
}

static int uurb_sync_frame(int *device, struct spa_buffer *buffer, int release)
{
    struct spa_meta_sync_timeline *timeline = spa_buffer_find_meta_data(
        buffer, SPA_META_SyncTimeline, sizeof(*timeline));
    if (!timeline || buffer->n_datas != 3) return -1;
    struct spa_data *data = &buffer->datas[release ? 2 : 1];
    if (data->type != SPA_DATA_SyncObj || data->fd < 0 || data->fd > INT_MAX) return -1;
    uint32_t handle = 0;
    if (uurb_sync_handle(device, (int)data->fd, &handle)) return -1;
    int result;
    if (release) {
        result = drmSyncobjTimelineSignal(*device, &handle, &timeline->release_point, 1);
#ifdef SPA_META_SYNC_TIMELINE_UNSCHEDULED_RELEASE
        if (!result) timeline->flags &= ~SPA_META_SYNC_TIMELINE_UNSCHEDULED_RELEASE;
#endif
    } else {
        struct timespec now;
        if (clock_gettime(CLOCK_MONOTONIC, &now)) { drmSyncobjDestroy(*device, handle); return -1; }
        int64_t deadline = (int64_t)now.tv_sec * 1000000000 + now.tv_nsec + 2000000000;
        do {
            result = drmSyncobjTimelineWait(*device, &handle, &timeline->acquire_point, 1,
                deadline, DRM_SYNCOBJ_WAIT_FLAGS_WAIT_FOR_SUBMIT, NULL);
        } while (result && errno == EINTR);
    }
    drmSyncobjDestroy(*device, handle);
    return result;
}
#endif
