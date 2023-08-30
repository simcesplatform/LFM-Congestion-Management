# -*- coding: utf-8 -*-

"""This module contains the message class for the selected offer messages."""

from __future__ import annotations
from typing import Union, List, Dict, Any

from tools.exceptions.messages import MessageValueError
from tools.message.abstract import AbstractResultMessage
from tools.tools import FullLogger

import datetime
from tools.datetime_tools import to_iso_format_datetime_string
from tools.message.block import QuantityBlock

LOGGER = FullLogger(__name__)

# Example:
# newMessage = SelectedOfferMessage(**{
#     "Type": "Request",
#     "SimulationId": to_iso_format_datetime_string(datetime.datetime.now()),
#     "SourceProcessId": "source1",
#     "MessageId": "messageid1",
#     "EpochNumber": 1,
#     "TriggeringMessageIds": ["messageid1.1","messageid1.2"],
#     "OfferIds": ["offer1", "offer2"]
# })


class SelectedOfferMessage(AbstractResultMessage):
    """Class containing all the attributes for a Request message."""

    # message type for these messages
    CLASS_MESSAGE_TYPE = "SelectedOffer"
    MESSAGE_TYPE_CHECK = True

    # Mapping from message JSON attributes to class attributes
    MESSAGE_ATTRIBUTES = {
        "OfferIds": "offer_ids"
    }

    OPTIONAL_ATTRIBUTES = []

    # Attribute names
    ATTRIBUTE_OFFERIDS = "OfferIds"

    # attributes whose value should be a QuantityBlock and the expected unit of measure.
    QUANTITY_BLOCK_ATTRIBUTES = {
    }

    # attributes whose value should be a Array Block.
    QUANTITY_ARRAY_BLOCK_ATTRIBUTES = {}

    # attributes whose value should be a Timeseries Block.
    TIMESERIES_BLOCK_ATTRIBUTES = []

    MESSAGE_ATTRIBUTES_FULL = {
        **AbstractResultMessage.MESSAGE_ATTRIBUTES_FULL,
        **MESSAGE_ATTRIBUTES
    }
    OPTIONAL_ATTRIBUTES_FULL = AbstractResultMessage.OPTIONAL_ATTRIBUTES_FULL + OPTIONAL_ATTRIBUTES
    QUANTITY_BLOCK_ATTRIBUTES_FULL = {
        **AbstractResultMessage.QUANTITY_BLOCK_ATTRIBUTES_FULL,
        **QUANTITY_BLOCK_ATTRIBUTES
    }
    QUANTITY_ARRAY_BLOCK_ATTRIBUTES_FULL = {
        **AbstractResultMessage.QUANTITY_ARRAY_BLOCK_ATTRIBUTES_FULL,
        **QUANTITY_ARRAY_BLOCK_ATTRIBUTES
    }
    TIMESERIES_BLOCK_ATTRIBUTES_FULL = (
        AbstractResultMessage.TIMESERIES_BLOCK_ATTRIBUTES_FULL +
        TIMESERIES_BLOCK_ATTRIBUTES
    )

    def __eq__(self, other: Any) -> bool:
        """Check that two RequestMessages represent the same message."""
        return (
            super().__eq__(other) and
            isinstance(other, SelectedOfferMessage) and
            self.offer_ids == other.offer_ids
        )

    @property
    def offer_ids(self) -> List[str]:
        """List of customer ids request is targeted at"""
        return self.__offer_ids

    @offer_ids.setter
    def offer_ids(self, offer_ids: Union[str, List[str]]):
        if self._check_offer_ids(offer_ids):
            self.__offer_ids = list(offer_ids)
            return

        raise MessageValueError("'{}' is an invalid value for CustomerIds.".format(offer_ids))

    @classmethod
    def _check_offer_ids(cls, offer_ids: Union[str, List[str]]) -> bool:
        if offer_ids is None:
            return False
        if (not isinstance(offer_ids, (str, list)) or len(offer_ids) == 0):
            return False
        if not isinstance(offer_ids, str):
            for offer_id in offer_ids:
                if not isinstance(offer_id, str):
                    return False
        return True

    @classmethod
    def from_json(cls, json_message: Dict[str, Any]) -> Union[SelectedOfferMessage, None]:
        if cls.validate_json(json_message):
            return SelectedOfferMessage(**json_message)
        return None


SelectedOfferMessage.register_to_factory()
