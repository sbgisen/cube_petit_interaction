#!/usr/bin/env python

# Copyright (c) 2026 SoftBank Corp.
#
# <<licensetext>>

"""UserStore の単体テスト (tmp_path 上の sqlite を使用)."""

import time

import pytest

from memory_person.src.user_store import UserStore


@pytest.fixture
def store(tmp_path):
    s = UserStore(str(tmp_path / 'users.db'))
    yield s
    s.close()


class TestCreateNewUser:

    def test_create_returns_defaults(self, store):
        user = store.create_new_user()
        assert user.confidence == 0.1
        assert user.interaction_count == 1
        assert user.display_name is None
        assert user.name_confidence == 0.0
        assert user.last_seen <= time.time()

    def test_created_user_is_persisted(self, store):
        user = store.create_new_user()
        fetched = store.get_user(user.user_id)
        assert fetched is not None
        assert fetched == user

    def test_user_ids_are_unique(self, store):
        ids = {store.create_new_user().user_id for _ in range(10)}
        assert len(ids) == 10


class TestGetUser:

    def test_missing_user_returns_none(self, store):
        assert store.get_user('no-such-id') is None

    def test_get_all_users_empty(self, store):
        assert store.get_all_users() == []

    def test_get_all_users_returns_all(self, store):
        created = [store.create_new_user() for _ in range(3)]
        users = store.get_all_users()
        assert len(users) == 3
        assert {u.user_id for u in users} == {u.user_id for u in created}


class TestUpdateInteraction:

    def test_increments_count_and_confidence(self, store):
        user = store.create_new_user()
        store.update_interaction(user.user_id)
        updated = store.get_user(user.user_id)
        assert updated.interaction_count == 2
        assert updated.confidence == pytest.approx(0.15)
        assert updated.last_seen >= user.last_seen

    def test_confidence_capped_at_one(self, store):
        user = store.create_new_user()
        for _ in range(30):  # 0.1 + 30 * 0.05 > 1.0
            store.update_interaction(user.user_id)
        assert store.get_user(user.user_id).confidence == 1.0

    def test_missing_user_is_noop(self, store):
        store.update_interaction('no-such-id')  # 例外にならない
        assert store.get_all_users() == []


class TestDisplayName:

    def test_set_candidate(self, store):
        user = store.create_new_user()
        store.set_display_name_candidate(user.user_id, 'テスト')
        updated = store.get_user(user.user_id)
        assert updated.display_name == 'テスト'
        assert updated.name_confidence == 0.4

    def test_confirm_name(self, store):
        user = store.create_new_user()
        store.set_display_name_candidate(user.user_id, 'テスト')
        store.confirm_display_name(user.user_id, 'テストさん')
        updated = store.get_user(user.user_id)
        assert updated.display_name == 'テストさん'
        assert updated.name_confidence == 0.8

    def test_candidate_missing_user_is_noop(self, store):
        store.set_display_name_candidate('no-such-id', 'x')
        assert store.get_all_users() == []

    def test_confirm_missing_user_is_noop(self, store):
        store.confirm_display_name('no-such-id', 'x')
        assert store.get_all_users() == []

    def test_candidate_does_not_touch_other_users(self, store):
        user_a = store.create_new_user()
        user_b = store.create_new_user()
        store.set_display_name_candidate(user_a.user_id, 'A')
        assert store.get_user(user_b.user_id).display_name is None


class TestPersistence:

    def test_data_survives_reopen(self, tmp_path):
        db_path = str(tmp_path / 'users.db')

        store = UserStore(db_path)
        user = store.create_new_user()
        store.confirm_display_name(user.user_id, 'テスト')
        store.close()

        reopened = UserStore(db_path)
        fetched = reopened.get_user(user.user_id)
        assert fetched is not None
        assert fetched.display_name == 'テスト'
        assert fetched.name_confidence == 0.8
        reopened.close()
