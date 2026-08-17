"""Chat image attachment persistence and multimodal conversion tests."""

import base64
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from langchain_core.messages import AIMessageChunk, HumanMessage

from my_agent_next.app.attachment_service import AttachmentService
from my_agent_next.app.chat_repository import ChatRepository
from my_agent_next.app.chat_service import ChatService


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class ChatAttachmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.repository = ChatRepository(root / "app.db")
        self.repository.create_thread("thread", "mabel", "Images")
        self.service = AttachmentService(root / "app.db", root / "attachments")

    def tearDown(self):
        self.temp.cleanup()

    def test_upload_bind_and_multimodal_content(self):
        attachment = self.service.save_upload("thread", "clock.png", PNG_1X1)
        self.assertEqual(attachment.mime_type, "image/png")
        self.assertNotIn("relative_path", attachment.public())

        message = self.repository.save_message("thread", "user", "分析图片")
        selected = self.service.validate_for_thread("thread", [attachment.id])
        self.service.bind(message.id, selected)
        stored = self.service.for_message(message.id)
        blocks = self.service.multimodal_content("分析图片", stored)

        self.assertEqual(blocks[0], {"type": "text", "text": "分析图片"})
        self.assertTrue(blocks[1]["image_url"]["url"].startswith("data:image/png;base64,"))
        with self.assertRaises(ValueError):
            self.service.validate_for_thread("thread", [attachment.id])

    def test_rejects_non_image_content(self):
        with self.assertRaisesRegex(ValueError, "仅支持"):
            self.service.save_upload("thread", "fake.png", b"not an image")

    def test_unbound_attachment_can_be_deleted(self):
        attachment = self.service.save_upload("thread", "clock.png", PNG_1X1)
        path = self.service.path_for(attachment)
        self.assertTrue(self.service.delete_unbound(attachment.id, "thread"))
        self.assertFalse(path.exists())


class _VisionModel:
    def __init__(self):
        self.messages = None

    async def astream(self, messages):
        self.messages = messages
        yield AIMessageChunk(content="已看到图片")


class ChatAttachmentRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_attachment_reaches_model_as_multimodal_human_message(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = ChatRepository(root / "app.db")
            repository.create_thread("thread", "mabel", "Images")
            attachments = AttachmentService(root / "app.db", root / "attachments")
            image = attachments.save_upload("thread", "clock.png", PNG_1X1)
            model = _VisionModel()
            agent = SimpleNamespace(skills=[], persona="", name="Mabel")
            with (
                patch("my_agent_next.app.chat_service.AgentProfileRepository.get", return_value=agent),
                patch("my_agent_next.app.chat_service._build_model", return_value=model),
            ):
                async for _ in ChatService(repository, attachments).stream_chat(
                    "mabel", "thread", "分析图片", SimpleNamespace(),
                    permission_mode="auto", attachment_ids=[image.id],
                ):
                    pass

            human = next(message for message in reversed(model.messages) if isinstance(message, HumanMessage))
            self.assertEqual(human.content[0], {"type": "text", "text": "分析图片"})
            self.assertEqual(human.content[1]["type"], "image_url")
            self.assertTrue(human.content[1]["image_url"]["url"].startswith("data:image/png;base64,"))
            user_message = next(message for message in repository.get_messages("thread") if message.role == "user")
            self.assertEqual(attachments.for_message(user_message.id)[0].id, image.id)


if __name__ == "__main__":
    unittest.main()
